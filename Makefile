# 開發用 Makefile

IMAGE_NAME=st-llm-backend-dev
CONTAINER_NAME=st-llm-backend-dev
PORT=10000

# 讀取本機 service_account.json 內容，傳給 container
GOOGLE_SERVICE_ACCOUNT_JSON=$(shell cat app/credentials/service_account.json | base64)

.PHONY: build
build:
	docker build -t $(IMAGE_NAME) .

.PHONY: run
run:
	docker run --rm -it \
	  -p $(PORT):10000 \
	  -e GOOGLE_SERVICE_ACCOUNT_JSON="$(GOOGLE_SERVICE_ACCOUNT_JSON)" \
	  --name $(CONTAINER_NAME) \
	  $(IMAGE_NAME)

.PHONY: stop
stop:
	docker stop $(CONTAINER_NAME) || true

.PHONY: logs
logs:
	docker logs -f $(CONTAINER_NAME)

.PHONY: bash
bash:
	docker exec -it $(CONTAINER_NAME) /bin/bash 