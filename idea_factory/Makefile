.DEFAULT_GOAL := test

port ?= 8000
service_name ?= idea-factory
version ?= 0.0.1
image_tag ?= $(service_name):$(version)
registry ?= 192.168.0.230:5005
registry_image ?= $(registry)/$(service_name):latest
docker_context ?= .
dockerfile ?= Dockerfile
env_file ?= .env
media_volume ?= idea-factory-media

.PHONY: test
test:
	python manage.py test

.PHONY: makemigrations
makemigrations:
	python manage.py makemigrations

.PHONY: migrate
migrate:
	python manage.py migrate --noinput

.PHONY: ensure-admin
ensure-admin:
	python manage.py ensure_default_admin

.PHONY: collectstatic
collectstatic:
	DJANGO_SETTINGS_MODULE=idea_factory.settings python manage.py collectstatic --noinput

.PHONY: env-file
env-file:
	@test -f $(env_file) || (cp .env.example $(env_file) && echo "Created $(env_file) from .env.example")

.PHONY: build-docker
build-docker: env-file
	docker build --file $(dockerfile) --tag $(image_tag) $(docker_context)

.PHONY: tag-docker
tag-docker:
	docker tag $(image_tag) $(registry_image)

.PHONY: push-docker
push-docker: tag-docker
	docker push $(registry_image)

.PHONY: build-push-docker
build-push-docker:
	$(MAKE) build-docker
	$(MAKE) push-docker

.PHONY: run-docker
run-docker:
	docker run --rm -p $(port):8000 \
		-v $(media_volume):/app/media \
		$(image_tag)

.PHONY: run-registry-docker
run-registry-docker:
	docker run --rm -p $(port):8000 \
		-v $(media_volume):/app/media \
		$(registry_image)

.PHONY: compose-up
compose-up:
	REGISTRY_IMAGE=$(registry_image) PORT=$(port) docker compose up -d

.PHONY: compose-down
compose-down:
	docker compose down

.PHONY: login-registry
login-registry:
	docker login $(registry)

.PHONY: clean-docker
clean-docker:
	-docker rmi $(image_tag)
	-docker rmi $(registry_image)
