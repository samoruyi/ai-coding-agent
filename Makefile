.PHONY: help bootstrap fmt lint test build-images compose-up compose-down \
        tf-init tf-apply tf-destroy ecr-login push-images deploy cleanup \
        helm-lint helm-template

# Defaults; override on the command line.
AWS_REGION       ?= us-west-2
PROJECT_NAME     ?= coding-agent
IMAGE_TAG        ?= 0.1.0
NAMESPACE        ?= coding-agent
RELEASE          ?= agent

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-22s %s\n",$$1,$$2}'

bootstrap: ## Provision the uv workspace venv (.venv) and copy .env
	./scripts/bootstrap.sh

fmt: ## Format Python (ruff) and Terraform
	uv run --with ruff ruff format apps/ packages/
	cd terraform && terraform fmt -recursive

lint: ## Lint Python (ruff) and Helm charts
	uv run --with ruff ruff check apps/ packages/
	helm lint helm/slack-gateway helm/temporal-worker helm/platform

test: ## Run unit tests (pytest) across the workspace
	uv run pytest -q

helm-template: ## Render umbrella chart against values.dev.yaml
	helm dependency update helm/platform
	helm template $(RELEASE) helm/platform -n $(NAMESPACE) -f helm/platform/values.dev.yaml

compose-up: ## Bring up local stack (Temporal + worker + gateway)
	docker compose up --build -d
	@echo "Temporal UI: http://localhost:8233"
	@echo "Slack gateway: http://localhost:8080/healthz"

compose-down: ## Tear down local stack
	docker compose down -v

build-images: ## Build both service images locally
	docker build -f apps/slack_gateway/Dockerfile  -t slack-gateway:$(IMAGE_TAG)  .
	docker build -f apps/temporal_worker/Dockerfile -t temporal-worker:$(IMAGE_TAG) .

# ---- AWS / EKS ----

tf-init: ## terraform init in envs/dev
	cd terraform/envs/dev && terraform init

tf-apply: ## terraform apply in envs/dev
	cd terraform/envs/dev && terraform apply

tf-destroy: ## terraform destroy in envs/dev
	cd terraform/envs/dev && terraform destroy

ecr-login: ## docker login to ECR
	aws ecr get-login-password --region $(AWS_REGION) | \
	  docker login --username AWS --password-stdin $$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$(AWS_REGION).amazonaws.com

push-images: build-images ecr-login ## Tag + push both images to ECR (tf-apply must have run)
	./scripts/build_images.sh $(IMAGE_TAG)

deploy: ## Install/upgrade the umbrella Helm release into the EKS cluster
	./scripts/deploy.sh $(IMAGE_TAG) $(NAMESPACE) $(RELEASE)

cleanup: ## Helm uninstall + terraform destroy
	./scripts/cleanup.sh $(NAMESPACE) $(RELEASE)
