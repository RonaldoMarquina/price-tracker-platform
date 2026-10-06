# Evidencia de Despliegue en AWS (Price Tracker Platform)

> **Fecha y hora de captura:** `2026-10-02 04:08:53 UTC`  
> **Cuenta de AWS:** `696835009022`  
> **Usuario IAM / Desplegador:** `arn:aws:iam::696835009022:user/price-tracker-deployer`  
> **Región AWS:** `us-east-1` (N. Virginia)

Este documento certifica el despliegue funcional y la operación en la nube de la plataforma **Price Tracker Platform** previo a su desaprovisionamiento preventivo por costos de infraestructura.

---

## 1. Distribución Global y Red de Contenidos (Amazon CloudFront)

- **Distribución Activa:**
```json
[
  {
    "Id": "E5GUBIP4TAZJ8",
    "DomainName": "d2ucxikcmvwuxh.cloudfront.net",
    "Status": "Deployed",
    "Enabled": true,
    "Comment": "price-tracker-demo CloudFront CDN"
  }
]
```
- **Dominio Público:** `https://d2ucxikcmvwuxh.cloudfront.net`
- **Configuración de Enrutamiento:**
  - `/` y estáticos: Enrutados a bucket S3 privado mediante Origin Access Control (OAC).
  - `/api/*`: Enrutado directamente al Application Load Balancer (ALB) con soporte de métodos dinámicos (`GET`, `POST`, `OPTIONS`).

---

## 2. Alojamiento de Frontend (Amazon S3)

- **Buckets de la plataforma:**
```json
[
  {
    "Name": "price-tracker-demo-frontend-demo-assets",
    "CreationDate": "2026-09-22T23:53:35+00:00"
  },
  {
    "Name": "price-tracker-demo-tfstate-696835009022",
    "CreationDate": "2026-09-22T23:35:11+00:00"
  }
]
```
- **Bucket Frontend:** `price-tracker-demo-frontend-demo-assets`
  - Aloja la aplicación de página única (SPA) construida con React, TypeScript y Vite.

---

## 3. Balanceador de Carga de Aplicaciones (AWS ALB)

- **Balanceador HTTP/HTTPS:**
```json
[
  {
    "Name": "price-tracker-demo-alb",
    "DNSName": "price-tracker-demo-alb-937570168.us-east-1.elb.amazonaws.com",
    "State": "active",
    "Type": "application",
    "VpcId": "vpc-03611c0b7808be105"
  }
]
```
- **Grupos de Destino (Target Groups):**
```json
[
  {
    "Name": "price-tracker-demo-tg",
    "Protocol": "HTTP",
    "Port": 8000,
    "TargetType": "ip"
  }
]
```

---

## 4. Contenedores Serverless (AWS Fargate & Amazon ECS)

- **Clúster ECS:** `price-tracker-demo-cluster`
- **Servicios Activos:**
```json
[
  {
    "Name": "price-tracker-demo-scraping-worker",
    "Status": "ACTIVE",
    "Desired": 1,
    "Running": 1,
    "TaskDef": "arn:aws:ecs:us-east-1:696835009022:task-definition/price-tracker-demo-scraping-worker:1"
  },
  {
    "Name": "price-tracker-demo-dlq-indexer",
    "Status": "ACTIVE",
    "Desired": 0,
    "Running": 0,
    "TaskDef": "arn:aws:ecs:us-east-1:696835009022:task-definition/price-tracker-demo-dlq-indexer:1"
  },
  {
    "Name": "price-tracker-demo-backend-api",
    "Status": "ACTIVE",
    "Desired": 1,
    "Running": 1,
    "TaskDef": "arn:aws:ecs:us-east-1:696835009022:task-definition/price-tracker-demo-backend-api:2"
  },
  {
    "Name": "price-tracker-demo-outbox-publisher",
    "Status": "ACTIVE",
    "Desired": 1,
    "Running": 1,
    "TaskDef": "arn:aws:ecs:us-east-1:696835009022:task-definition/price-tracker-demo-outbox-publisher:2"
  }
]
```
- **Tareas ECS en Ejecución:**
```json
[
  "arn:aws:ecs:us-east-1:696835009022:task/price-tracker-demo-cluster/1b6834423a18489493862b5872fa94d9",
  "arn:aws:ecs:us-east-1:696835009022:task/price-tracker-demo-cluster/7cef662bcb2042c8856024d0856b41d2",
  "arn:aws:ecs:us-east-1:696835009022:task/price-tracker-demo-cluster/a22f16d8136b4d9bb531be323d48180a"
]
```
- **Descripción de componentes en ECS:**
  1. `price-tracker-demo-backend-api`: API REST construida en FastAPI con Uvicorn.
  2. `price-tracker-demo-scraping-worker`: Worker asíncrono para extracción y scraping periódico.
  3. `price-tracker-demo-outbox-publisher`: Publicador de eventos transaccionales desde PostgreSQL hacia SQS.
  4. `price-tracker-demo-dlq-indexer`: Indexador de mensajes fallidos en Dead Letter Queue.

---

## 5. Base de Datos Relacional (Amazon RDS PostgreSQL)

- **Instancia de Base de Datos Administrada:**
```json
[
  {
    "Identifier": "price-tracker-demo-postgres",
    "Engine": "postgres",
    "Version": "16.13",
    "Status": "available",
    "Endpoint": "price-tracker-demo-postgres.ck98iqyw2isf.us-east-1.rds.amazonaws.com",
    "Port": 5432,
    "Storage": 20,
    "Class": "db.t4g.micro"
  }
]
```
- **Motor:** PostgreSQL (Multi-tabla relacional con soporte transaccional para Catálogo, Observaciones de Precios y Outbox).

---

## 6. Mensajería Asíncrona (Amazon SQS & Dead Letter Queue)

- **Colas de Mensajería:**
```json
[
  {
    "url": "https://sqs.us-east-1.amazonaws.com/696835009022/price-tracker-demo-scraping-jobs",
    "attributes": {
      "ApproximateNumberOfMessages": "0",
      "ApproximateNumberOfMessagesNotVisible": "0",
      "QueueArn": "arn:aws:sqs:us-east-1:696835009022:price-tracker-demo-scraping-jobs"
    }
  },
  {
    "url": "https://sqs.us-east-1.amazonaws.com/696835009022/price-tracker-demo-scraping-jobs-dlq",
    "attributes": {
      "ApproximateNumberOfMessages": "0",
      "ApproximateNumberOfMessagesNotVisible": "0",
      "QueueArn": "arn:aws:sqs:us-east-1:696835009022:price-tracker-demo-scraping-jobs-dlq"
    }
  }
]
```
- **Propósito:** Desacopla completamente las peticiones HTTP del procesamiento intensivo de scraping, con reintentos automáticos y DLQ para aislamiento de fallos.

---

## 7. Automatización y Tareas Programadas (Amazon EventBridge)

- **Programadores Serverless:**
```json
[
  {
    "Name": "price-tracker-demo-dispatcher",
    "State": "DISABLED",
    "Arn": "arn:aws:scheduler:us-east-1:696835009022:schedule/default/price-tracker-demo-dispatcher"
  }
]
```

---

## 8. Seguridad y Almacén de Secretos (AWS Secrets Manager)

- **Secretos Gestionados (sin exposición de claves):**
```json
[
  {
    "Name": "price-tracker/internal-api-key-demo",
    "Arn": "arn:aws:secretsmanager:us-east-1:696835009022:secret:price-tracker/internal-api-key-demo-ecyz6E",
    "LastChanged": "2026-09-22T23:35:31.226000+00:00"
  }
]
```
- Las credenciales de RDS y las llaves internas de API se inyectaron directamente en tiempo de ejecución a los contenedores Fargate mediante integración nativa con Secrets Manager.

---

## 9. Observabilidad y Logs (Amazon CloudWatch)

- **Grupos de Logs:**
```json
[
  {
    "Name": "/ecs/price-tracker-demo",
    "StoredBytes": 4077987
  }
]
```

---

## 10. Registro de Contenedores Docker (Amazon ECR)

- **Repositorios de Imágenes:**
```json
[
  {
    "Name": "price-tracker-backend",
    "Uri": "696835009022.dkr.ecr.us-east-1.amazonaws.com/price-tracker-backend"
  },
  {
    "Name": "price-tracker-worker",
    "Uri": "696835009022.dkr.ecr.us-east-1.amazonaws.com/price-tracker-worker"
  }
]
```

---

## Conclusión

El entorno en AWS fue desplegado de manera nativa y automatizada mediante **Terraform (IaC)**, demostrando escalabilidad horizontal, alta disponibilidad en componentes administrados y desacoplamiento de capas bajo las mejores prácticas de arquitectura en la nube.
