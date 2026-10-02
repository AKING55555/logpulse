PROJECT_NAME := logpulse
COMPOSE_FILE := docker-compose.yml

.PHONY: help up down logs reset ps init-aws test-env

help:
	@echo "LogPulse Local Development Management"
	@echo "Targets:"
	@echo "  up       - Start MySQL (3307), Redis (6380), and LocalStack (4566)"
	@echo "  down     - Stop containers without removing volumes"
	@echo "  logs     - Stream container logs"
	@echo "  reset    - Destroy volumes, recreate containers, and reinitialize AWS resources"
	@echo "  ps       - Check health status of logpulse services"
	@echo "  init-aws - Run LocalStack resource initialization"

up:
	docker compose -p $(PROJECT_NAME) -f $(COMPOSE_FILE) up -d --wait
	@$(MAKE) init-aws

down:
	docker compose -p $(PROJECT_NAME) -f $(COMPOSE_FILE) down

logs:
	docker compose -p $(PROJECT_NAME) -f $(COMPOSE_FILE) logs -f

reset:
	docker compose -p $(PROJECT_NAME) -f $(COMPOSE_FILE) down -v --remove-orphans
	docker compose -p $(PROJECT_NAME) -f $(COMPOSE_FILE) up -d --wait
	@$(MAKE) init-aws

ps:
	docker compose -p $(PROJECT_NAME) -f $(COMPOSE_FILE) ps

init-aws:
	docker exec logpulse-localstack /bin/bash -c "chmod +x /etc/localstack/init/ready.d/init-localstack.sh && /etc/localstack/init/ready.d/init-localstack.sh"
