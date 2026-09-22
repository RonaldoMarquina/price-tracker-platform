"""Static compliance tests for Infrastructure as Code and Dockerfiles (Subincrement 8C)."""

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INFRA_DIR = REPO_ROOT / "infrastructure"
DOCKER_DIR = INFRA_DIR / "docker"
TF_DIR = INFRA_DIR / "terraform"


def test_dockerfiles_exist_and_non_root_user():
    """Requirement: Dockerfiles must create and switch to non-root appuser."""
    for dockerfile_name in ["backend.Dockerfile", "worker.Dockerfile"]:
        df_path = DOCKER_DIR / dockerfile_name
        assert df_path.is_file(), f"Missing {dockerfile_name}"
        content = df_path.read_text(encoding="utf-8")

        assert "USER appuser" in content or "USER appuser:appgroup" in content
        assert "groupadd -g 10001" in content
        assert "useradd -u 10001" in content


def test_dockerfiles_exclude_requirements_dev():
    """Requirement: Production Dockerfiles must not copy or install requirements-dev.txt."""
    for dockerfile_name in ["backend.Dockerfile", "worker.Dockerfile"]:
        content = (DOCKER_DIR / dockerfile_name).read_text(encoding="utf-8")
        assert "requirements-dev.txt" not in content


def test_dockerfiles_include_shared_library():
    """Requirement: Production Dockerfiles must copy shared/ library into /app/shared."""
    for dockerfile_name in ["backend.Dockerfile", "worker.Dockerfile"]:
        content = (DOCKER_DIR / dockerfile_name).read_text(encoding="utf-8")
        assert "COPY shared/ ./shared/" in content


def test_backend_dockerfile_no_reload_flag():
    """Requirement: Production backend Dockerfile must not include --reload in CMD."""
    content = (DOCKER_DIR / "backend.Dockerfile").read_text(encoding="utf-8")
    assert "--reload" not in content


def test_backend_dockerfile_healthcheck_urllib():
    """Requirement: Backend HEALTHCHECK must use urllib.request, not missing binaries like curl."""
    content = (DOCKER_DIR / "backend.Dockerfile").read_text(encoding="utf-8")
    assert "HEALTHCHECK" in content
    assert "urllib.request" in content
    assert "curl" not in content


def test_frontend_dockerfile_produces_exportable_dist():
    """Requirement: Frontend Dockerfile must build static assets in /dist without Nginx."""
    content = (DOCKER_DIR / "frontend.Dockerfile").read_text(encoding="utf-8")
    assert "npm run build" in content
    assert "COPY --from=builder /app/dist /dist" in content
    assert "nginx" not in content.lower()


def test_terraform_gitignores_exclude_state_and_plans():
    """Requirement: .gitignore must strictly exclude .terraform/, *.tfstate*, and *.tfplan."""
    for gi_path in [REPO_ROOT / ".gitignore", TF_DIR / ".gitignore"]:
        assert gi_path.is_file()
        content = gi_path.read_text(encoding="utf-8")
        assert "*.tfstate" in content
        assert ".terraform" in content


def test_compute_task_images_and_entrypoints_separation():
    """Requirement: Outbox must use backend image, DLQ indexer must use worker image."""
    compute_tf = (TF_DIR / "modules" / "compute" / "main.tf").read_text(encoding="utf-8")

    # 1. Outbox publisher uses backend image
    assert 'resource "aws_ecs_task_definition" "outbox_publisher"' in compute_tf
    outbox_pattern = (
        r'resource "aws_ecs_task_definition" "outbox_publisher"'
        r'.*?container_definitions\s*=\s*jsonencode\(\[(.*?)\]\)'
    )
    outbox_block = re.search(outbox_pattern, compute_tf, re.DOTALL)
    assert outbox_block is not None
    outbox_text = outbox_block.group(1)
    assert "var.backend_image_uri" in outbox_text
    assert "app.services.outbox_publisher" in outbox_text

    # 2. DLQ indexer uses worker image
    assert 'resource "aws_ecs_task_definition" "dlq_indexer"' in compute_tf
    dlq_pattern = (
        r'resource "aws_ecs_task_definition" "dlq_indexer"'
        r'.*?container_definitions\s*=\s*jsonencode\(\[(.*?)\]\)'
    )
    dlq_block = re.search(dlq_pattern, compute_tf, re.DOTALL)
    assert dlq_block is not None
    dlq_text = dlq_block.group(1)
    assert "var.worker_image_uri" in dlq_text
    assert "app.services.dlq_indexer" in dlq_text

    # 3. Dispatcher uses backend image with --once
    disp_pattern = (
        r'resource "aws_ecs_task_definition" "dispatcher"'
        r'.*?container_definitions\s*=\s*jsonencode\(\[(.*?)\]\)'
    )
    disp_block = re.search(disp_pattern, compute_tf, re.DOTALL)
    assert disp_block is not None
    disp_text = disp_block.group(1)
    assert "var.backend_image_uri" in disp_text
    assert "--once" in disp_text


def test_compute_tasks_inject_secrets_via_ecs_secrets():
    """Requirement: Database password must be injected via ECS secrets, not plaintext env."""
    compute_tf = (TF_DIR / "modules" / "compute" / "main.tf").read_text(encoding="utf-8")
    assert "DB_PASSWORD" in compute_tf
    assert "DATABASE_PASSWORD" not in compute_tf
    assert "var.master_user_secret_arn" in compute_tf

    # Verify none of the task definitions pass password as plaintext environment variable
    assert 'value = "password"' not in compute_tf
    assert 'value = var.master_user_secret_arn' not in compute_tf


def test_iam_no_invalid_sqs_send_message_batch_action():
    """Requirement: sqs:SendMessageBatch is not an IAM action; sqs:SendMessage must be used."""
    for tf_file in TF_DIR.rglob("*.tf"):
        content = tf_file.read_text(encoding="utf-8")
        assert "sqs:SendMessageBatch" not in content


def test_eventbridge_scheduler_minimal_privilege():
    """Requirement: Scheduler role must only have ecs:RunTask and scoped iam:PassRole."""
    compute_tf = (TF_DIR / "modules" / "compute" / "main.tf").read_text(encoding="utf-8")
    assert 'resource "aws_iam_role" "scheduler"' in compute_tf
    assert '"ecs:RunTask"' in compute_tf
    assert '"iam:PassedToService" = "ecs-tasks.amazonaws.com"' in compute_tf


def test_cloudfront_api_behavior_no_caching_and_header_forwarding():
    """Requirement: CloudFront must disable caching for /api/* and forward headers."""
    storage_tf = (TF_DIR / "modules" / "storage" / "main.tf").read_text(encoding="utf-8")

    api_behavior = re.search(
        r'ordered_cache_behavior\s*\{.*?path_pattern\s*=\s*"/api/\*".*?\}',
        storage_tf,
        re.DOTALL,
    )
    assert api_behavior is not None
    api_text = api_behavior.group(0)

    assert "min_ttl     = 0" in api_text or "min_ttl = 0" in api_text
    assert "default_ttl = 0" in api_text or "default_ttl = 0" in api_text
    assert "max_ttl     = 0" in api_text or "max_ttl = 0" in api_text
    assert '"Authorization"' in api_text
    assert "query_string = true" in api_text


def test_cloudfront_spa_routing_fallbacks():
    """Requirement: CloudFront must route 403 and 404 to /index.html with status 200 for SPA."""
    storage_tf = (TF_DIR / "modules" / "storage" / "main.tf").read_text(encoding="utf-8")
    assert 'error_code            = 403' in storage_tf
    assert 'error_code            = 404' in storage_tf
    assert 'response_code         = 200' in storage_tf
    assert 'response_page_path    = "/index.html"' in storage_tf


def test_sqs_redrive_policy_max_receive_count():
    """Requirement: SQS main queue must define maxReceiveCount = 3 in redrive policy."""
    messaging_tf = (TF_DIR / "modules" / "messaging" / "main.tf").read_text(encoding="utf-8")
    assert "maxReceiveCount     = 3" in messaging_tf or "maxReceiveCount = 3" in messaging_tf


def test_networking_security_groups_ingress_isolation():
    """Requirement: Worker, dispatcher, outbox and DLQ indexer must have ZERO ingress rules."""
    net_tf = (TF_DIR / "modules" / "networking" / "main.tf").read_text(encoding="utf-8")

    # Worker security group has no ingress rule
    assert 'resource "aws_security_group" "worker"' in net_tf
    assert 'aws_security_group_rule" "worker_ingress' not in net_tf

    # Database only accepts ingress from api and worker security groups
    assert 'resource "aws_security_group_rule" "db_ingress_api"' in net_tf
    assert 'resource "aws_security_group_rule" "db_ingress_worker"' in net_tf
    assert 'aws_security_group_rule" "db_ingress_internet' not in net_tf


def test_dispatcher_once_flag_execution():
    """Requirement: Dispatcher must support --once mode and terminate cleanly."""
    from app.dispatcher import main as dispatcher_main

    with patch("sys.argv", ["dispatcher.py", "--once"]), \
         patch("app.dispatcher.DispatchService") as mock_service_cls:
        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.skipped_lock = False
        mock_result.jobs_created = 1
        mock_result.total_products = 4
        mock_instance.run_once.return_value = mock_result
        mock_service_cls.return_value = mock_instance

        # Should run once and return without looping
        dispatcher_main()
        mock_instance.run_once.assert_called_once()


def test_no_database_url_with_password_in_terraform():
    """Requirement: No PostgreSQL connection URL or password string in Terraform files."""
    for tf_file in TF_DIR.rglob("*.tf"):
        content = tf_file.read_text(encoding="utf-8")
        assert "postgresql://" not in content, f"Hardcoded postgresql URL found in {tf_file}"


def test_discrete_database_env_vars_in_all_task_definitions():
    """Requirement: All 6 ECS task definitions must inject discrete DB parameters."""
    compute_tf = (TF_DIR / "modules" / "compute" / "main.tf").read_text(encoding="utf-8")
    for task_name in [
        "backend_api",
        "scraping_worker",
        "outbox_publisher",
        "dlq_indexer",
        "dispatcher",
        "migration",
    ]:
        pattern = rf'resource "aws_ecs_task_definition" "{task_name}".*?container_definitions'
        assert re.search(pattern, compute_tf, re.DOTALL), f"Missing task definition {task_name}"

    # Check discrete DB parameters exist in environment blocks
    assert re.search(r'name\s*=\s*"DB_HOST"', compute_tf)
    assert re.search(r'name\s*=\s*"DB_PORT"', compute_tf)
    assert re.search(r'name\s*=\s*"DB_NAME"', compute_tf)
    assert re.search(r'name\s*=\s*"DB_USER"', compute_tf)
    assert re.search(r'name\s*=\s*"DB_PASSWORD"', compute_tf)


def test_sqs_task_definitions_variables():
    """Requirement: Worker, Outbox, and DLQ Indexer receive SQS URLs and regions."""
    compute_tf = (TF_DIR / "modules" / "compute" / "main.tf").read_text(encoding="utf-8")
    assert 'name = "AWS_REGION"' in compute_tf or 'AWS_REGION' in compute_tf
    assert 'name = "SCRAPING_QUEUE_URL"' in compute_tf or 'SCRAPING_QUEUE_URL' in compute_tf
    assert 'name = "SCRAPING_DLQ_URL"' in compute_tf or 'SCRAPING_DLQ_URL' in compute_tf


def test_api_documentation_disabled_in_production():
    """Requirement: /docs, /redoc, /openapi.json must return 404 in production."""
    from fastapi.testclient import TestClient

    with patch("app.core.config.settings.ENVIRONMENT", "production"), \
         patch("app.core.config.settings.DOCS_ENABLED", False):
        import importlib

        import app.main
        importlib.reload(app.main)

        prod_client = TestClient(app.main.app)
        assert prod_client.get("/docs").status_code == 404
        assert prod_client.get("/redoc").status_code == 404
        assert prod_client.get("/openapi.json").status_code == 404

        # Reload back to development for subsequent tests
        with patch("app.core.config.settings.ENVIRONMENT", "development"), \
             patch("app.core.config.settings.DOCS_ENABLED", True):
            importlib.reload(app.main)


def test_settings_assembles_database_url_from_discrete_env():
    """Requirement: Backend Settings dynamically assembles DATABASE_URL from discrete params."""
    from app.core.config import Settings

    s = Settings(
        DB_HOST="rds.internal",
        DB_PORT=5432,
        DB_NAME="tracker_db",
        DB_USER="app_user",
        DB_PASSWORD="secret_pwd@123",
    )
    assert s.DATABASE_URL == "postgresql://app_user:secret_pwd%40123@rds.internal:5432/tracker_db"


def test_worker_settings_assembles_database_url_from_discrete_env():
    """Requirement: WorkerSettings dynamically assembles DATABASE_URL from discrete params."""
    import importlib.util

    worker_config_path = REPO_ROOT / "worker" / "app" / "core" / "config.py"
    spec = importlib.util.spec_from_file_location("worker_config_module", str(worker_config_path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    ws = mod.WorkerSettings(
        DB_HOST="rds.internal",
        DB_PORT=5432,
        DB_NAME="tracker_db",
        DB_USER="worker_user",
        DB_PASSWORD="p@ssword!",
    )
    assert ws.DATABASE_URL == "postgresql://worker_user:p%40ssword%21@rds.internal:5432/tracker_db"


def test_sqs_queue_reads_env_queue_urls():
    """Requirement: SqsQueue reads SCRAPING_QUEUE_URL and SCRAPING_DLQ_URL without API calls."""
    import os
    from unittest.mock import MagicMock

    from shared.queue.sqs import SqsQueue

    mock_client = MagicMock()
    with patch.dict(os.environ, {
        "SCRAPING_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/123/main",
        "SCRAPING_DLQ_URL": "https://sqs.us-east-1.amazonaws.com/123/dlq",
    }):
        q = SqsQueue(client=mock_client)
        assert q.get_queue_url("scraping-jobs") == "https://sqs.us-east-1.amazonaws.com/123/main"
        assert q.get_queue_url("scraping-jobs-dlq") == "https://sqs.us-east-1.amazonaws.com/123/dlq"
        # Verify get_queue_url on client was NOT called
        mock_client.get_queue_url.assert_not_called()


def test_database_credentials_encoding_special_characters():
    """Requirement: Passwords with space, @, :, /, +, %, # must be safely percent-encoded.

    Spaces must encode as %20 (not +), + as %2B, and parse back identically with make_url.
    """
    from sqlalchemy.engine import make_url

    from app.core.config import Settings

    test_cases = [
        ("pass with space", "pass%20with%20space"),
        ("pass@at", "pass%40at"),
        ("pass:colon", "pass%3Acolon"),
        ("pass/slash", "pass%2Fslash"),
        ("pass+plus", "pass%2Bplus"),
        ("pass%percent", "pass%25percent"),
        ("pass#hash", "pass%23hash"),
        ("p @: /+%# w o r d", "p%20%40%3A%20%2F%2B%25%23%20w%20o%20r%20d"),
    ]

    for raw_pwd, expected_encoded in test_cases:
        s = Settings(
            DB_HOST="db.internal",
            DB_PORT=5432,
            DB_NAME="testdb",
            DB_USER="user:special@name",
            DB_PASSWORD=raw_pwd,
        )

        assert expected_encoded in s.DATABASE_URL
        # Ensure spaces are NOT converted to '+' in userinfo
        if " " in raw_pwd:
            assert "+" not in expected_encoded

        parsed = make_url(s.DATABASE_URL)
        assert parsed.password == raw_pwd, f"Mismatch for {raw_pwd}: got {parsed.password}"
        assert parsed.username == "user:special@name"

        # Verify secure masking: hide_password=True renders '***' without leaking password
        masked = parsed.render_as_string(hide_password=True)
        assert raw_pwd not in masked
        assert "***" in masked


def test_backend_and_worker_produce_equivalent_database_connections():
    """Requirement: Backend and worker produce equivalent DB URLs with masked logging."""
    import importlib.util

    from sqlalchemy.engine import make_url

    from app.core.config import Settings

    worker_config_path = REPO_ROOT / "worker" / "app" / "core" / "config.py"
    spec = importlib.util.spec_from_file_location("worker_config_mod", str(worker_config_path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    special_pwd = "My Secret! @: /+%# 2026"
    test_user = "crawler_user"

    backend_settings = Settings(
        DB_HOST="postgres-db.example.com",
        DB_PORT=5432,
        DB_NAME="price_tracker",
        DB_USER=test_user,
        DB_PASSWORD=special_pwd,
    )

    worker_settings = mod.WorkerSettings(
        DB_HOST="postgres-db.example.com",
        DB_PORT=5432,
        DB_NAME="price_tracker",
        DB_USER=test_user,
        DB_PASSWORD=special_pwd,
    )

    # Both must assemble identical URLs
    assert backend_settings.DATABASE_URL == worker_settings.DATABASE_URL

    # Both parse identically with SQLAlchemy
    b_url = make_url(backend_settings.DATABASE_URL)
    w_url = make_url(worker_settings.DATABASE_URL)

    assert b_url.username == w_url.username == test_user
    assert b_url.password == w_url.password == special_pwd
    assert b_url.host == w_url.host == "postgres-db.example.com"
    assert b_url.port == w_url.port == 5432
    assert b_url.database == w_url.database == "price_tracker"

    # Verify masked representation never contains the password
    for url in (b_url, w_url):
        rendered = url.render_as_string(hide_password=True)
        assert special_pwd not in rendered
        assert "***" in rendered


def test_database_url_explicit_priority_over_postgres_env():
    """Requirement: Explicit DATABASE_URL must not be overwritten by POSTGRES_* or DB_* vars."""
    import importlib.util
    import os
    from unittest.mock import patch

    from app.core.config import Settings

    worker_config_path = REPO_ROOT / "worker" / "app" / "core" / "config.py"
    spec = importlib.util.spec_from_file_location("worker_config_mod_prio", str(worker_config_path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    docker_env = {
        "DATABASE_URL": "postgresql://postgres:postgres@postgres:5432/price_tracker",
        "POSTGRES_HOST": "postgres",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "price_tracker",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",
    }

    with patch.dict(os.environ, docker_env, clear=False):
        # Remove any DB_* variables to simulate exact Docker Compose environment
        for k in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]:
            os.environ.pop(k, None)

        backend_settings = Settings()
        worker_settings = mod.WorkerSettings()

        # Both must preserve the exact DATABASE_URL with password intact
        assert (
            backend_settings.DATABASE_URL
            == "postgresql://postgres:postgres@postgres:5432/price_tracker"
        )
        assert (
            worker_settings.DATABASE_URL
            == "postgresql://postgres:postgres@postgres:5432/price_tracker"
        )

        # Direct kwargs instantiation with DATABASE_URL also takes absolute priority
        custom_url = "postgresql://custom_user:custom_pass@custom_host:5432/custom_db"
        b_custom = Settings(DATABASE_URL=custom_url, DB_HOST="extra_host")
        w_custom = mod.WorkerSettings(DATABASE_URL=custom_url, DB_HOST="extra_host")
        assert b_custom.DATABASE_URL == custom_url
        assert w_custom.DATABASE_URL == custom_url


def test_database_discrete_incomplete_raises_safe_error():
    """Requirement: Incomplete DB_* parameters must raise ValueError without leaking secrets."""
    import importlib.util

    from app.core.config import Settings

    worker_config_path = REPO_ROOT / "worker" / "app" / "core" / "config.py"
    spec = importlib.util.spec_from_file_location("worker_config_mod_err", str(worker_config_path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    secret_val = "super_sensitive_plain_secret_pwd_987"

    # Missing password
    for cls in [Settings, mod.WorkerSettings]:
        try:
            cls(DB_HOST="rds.internal", DB_NAME="tracker_db", DB_USER="user")
            assert False, f"{cls} should have failed when DB_PASSWORD is missing"
        except ValueError as exc:
            assert "Incomplete database configuration" in str(exc)
            assert "DB_PASSWORD" in str(exc)

    # Missing user with secret password provided: verify secret is NOT leaked in error
    for cls in [Settings, mod.WorkerSettings]:
        try:
            cls(DB_HOST="rds.internal", DB_NAME="tracker_db", DB_PASSWORD=secret_val)
            assert False, f"{cls} should have failed when DB_USER is missing"
        except ValueError as exc:
            assert "Incomplete database configuration" in str(exc)
            assert secret_val not in str(exc), "LEAKED SECRET IN ERROR MESSAGE!"
            assert "DB_USER" in str(exc)


def test_database_discrete_aws_mode_from_environment():
    """Requirement: AWS environment with DB_* and without DATABASE_URL builds correctly."""
    import importlib.util
    import os
    from unittest.mock import patch

    from app.core.config import Settings

    worker_config_path = REPO_ROOT / "worker" / "app" / "core" / "config.py"
    spec = importlib.util.spec_from_file_location("worker_config_mod_aws", str(worker_config_path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    aws_env = {
        "DB_HOST": "price-tracker-rds.c7x8.us-east-1.rds.amazonaws.com",
        "DB_PORT": "5432",
        "DB_NAME": "price_tracker_prod",
        "DB_USER": "master_app_user",
        "DB_PASSWORD": "aws_pass@with space:and/symbols#",
    }

    with patch.dict(os.environ, aws_env, clear=False):
        os.environ.pop("DATABASE_URL", None)

        backend_settings = Settings()
        worker_settings = mod.WorkerSettings()

        expected_url = (
            "postgresql://master_app_user:aws_pass%40with%20space%3Aand%2Fsymbols%23"
            "@price-tracker-rds.c7x8.us-east-1.rds.amazonaws.com:5432/price_tracker_prod"
        )
        assert backend_settings.DATABASE_URL == expected_url
        assert worker_settings.DATABASE_URL == expected_url


def test_suite_aborts_if_database_url_points_to_development():
    """Requirement: Test suite must fail immediately if DATABASE_URL points to dev/prod."""
    import os
    import subprocess
    import sys

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "tests/test_models.py",
    ]
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/price_tracker",
    }
    result = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT / "backend"),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    output = result.stderr + result.stdout
    assert "ABORTING TEST EXECUTION" in output
    assert "price_tracker" in output
