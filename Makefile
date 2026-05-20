# Delegate Docker and app targets to idea_factory/
IDEA_FACTORY_DIR := idea_factory

.PHONY: build-push-docker build-docker push-docker run-docker run-registry-docker compose-up compose-down ensure-admin migrate test

%:
	@$(MAKE) -C $(IDEA_FACTORY_DIR) $@

build-push-docker:
	@$(MAKE) -C $(IDEA_FACTORY_DIR) build-push-docker

build-docker:
	@$(MAKE) -C $(IDEA_FACTORY_DIR) build-docker

push-docker:
	@$(MAKE) -C $(IDEA_FACTORY_DIR) push-docker

run-docker:
	@$(MAKE) -C $(IDEA_FACTORY_DIR) run-docker

run-registry-docker:
	@$(MAKE) -C $(IDEA_FACTORY_DIR) run-registry-docker

compose-up:
	@$(MAKE) -C $(IDEA_FACTORY_DIR) compose-up

compose-down:
	@$(MAKE) -C $(IDEA_FACTORY_DIR) compose-down

ensure-admin:
	@$(MAKE) -C $(IDEA_FACTORY_DIR) ensure-admin

migrate:
	@$(MAKE) -C $(IDEA_FACTORY_DIR) migrate

test:
	@$(MAKE) -C $(IDEA_FACTORY_DIR) test
