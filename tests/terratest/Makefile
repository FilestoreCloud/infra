# Terratest In-Place Infrastructure Test Runner
ENV ?= dev
AWS_REGION ?= ap-southeast-1
TIMEOUT ?= 15m

.PHONY: help test-all test-stage test-resilience test-compile tidy

help:
	@echo "🛠️  Terratest In-Place Test Automation Commands:"
	@echo "  make test-all                - Run all in-place audit tests on active environment"
	@echo "  make test-stage STAGE=01     - Run specific stage (01-networking, ..., 07-observability, 08-resilience)"
	@echo "  make test-resilience         - Run Stage 08 Chaos & Self-Healing Resilience test (ECS Fargate failover)"
	@echo "  make test-compile            - Verify test compilation without calling AWS"
	@echo "  make tidy                    - Clean and download dependencies"

test-compile:
	@echo "🔨 Checking compilation..."
	go test -c -o /dev/null
	@echo "✅ All tests compiled cleanly."

tidy:
	go mod tidy

test-resilience:
	@echo "💥 Running Chaos & Self-Healing Resilience test (ENV=$(ENV), Region=$(AWS_REGION))..."
	ENV=$(ENV) AWS_REGION=$(AWS_REGION) go test -v -run "TestInPlaceResilience" -timeout $(TIMEOUT)

test-all:
	@echo "🚀 Running complete In-Place infrastructure test suite (ENV=$(ENV), Region=$(AWS_REGION))..."
	ENV=$(ENV) AWS_REGION=$(AWS_REGION) go test -v -run "TestInPlace" -timeout $(TIMEOUT)

test-stage:
	@if [ -z "$(STAGE)" ]; then \
		echo "❌ Please provide STAGE parameter. Example: make test-stage STAGE=01"; \
		exit 1; \
		fi
	@echo "🔍 Running Stage $(STAGE) verification..."
	@case "$(STAGE)" in \
		01|networking) ENV=$(ENV) AWS_REGION=$(AWS_REGION) go test -v -run "TestInPlaceNetworking" ;; \
		02|security)   ENV=$(ENV) AWS_REGION=$(AWS_REGION) go test -v -run "TestInPlaceSecurity" ;; \
		03|storage)    ENV=$(ENV) AWS_REGION=$(AWS_REGION) go test -v -run "TestInPlaceStorage" ;; \
		04|database)   ENV=$(ENV) AWS_REGION=$(AWS_REGION) go test -v -run "TestInPlaceDatabase" ;; \
		05|compute)    ENV=$(ENV) AWS_REGION=$(AWS_REGION) go test -v -run "TestInPlaceCompute" ;; \
		06|superadmin) ENV=$(ENV) AWS_REGION=$(AWS_REGION) go test -v -run "TestInPlaceSuperAdmin" ;; \
		07|observability) ENV=$(ENV) AWS_REGION=$(AWS_REGION) go test -v -run "TestInPlaceObservability" ;; \
		08|resilience) ENV=$(ENV) AWS_REGION=$(AWS_REGION) go test -v -run "TestInPlaceResilience" ;; \
		*) echo "❌ Unknown stage: $(STAGE). Valid values: 01, 02, 03, 04, 05, 06, 07, 08"; exit 1 ;; \
	esac
