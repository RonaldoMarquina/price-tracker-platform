from setuptools import setup

setup(
    name="price-tracker-shared",
    version="0.1.0",
    packages=["shared", "shared.queue", "shared.schemas"],
    package_dir={"shared": "."},
)
