#!/bin/bash
# Comprehensive Test Suite for ON1Builder
# This script will run tests for all components of the project

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PROJECT_DIR}/data/logs"
TEST_LOG="${LOG_DIR}/comprehensive_test_$(date +%Y%m%d_%H%M%S).log"

# Create log directory if it doesn't exist
mkdir -p "${LOG_DIR}"

# Initialize log file
echo "ON1Builder Comprehensive Test Suite" > "${TEST_LOG}"
echo "Started at: $(date)" >> "${TEST_LOG}"
echo "======================================" >> "${TEST_LOG}"

# Function for printing section headers
print_section() {
    echo -e "\n${YELLOW}=============== $1 ===============${NC}"
    echo -e "\n=============== $1 ===============" >> "${TEST_LOG}"
}

# Function for running tests with proper output
run_test() {
    description=$1
    command=$2
    
    echo -e "\n${YELLOW}Testing: ${description}${NC}"
    echo -e "\nTesting: ${description}" >> "${TEST_LOG}"
    echo "Command: ${command}" >> "${TEST_LOG}"
    
    if eval "${command} >> \"${TEST_LOG}\" 2>&1"; then
        echo -e "${GREEN}✓ PASSED: ${description}${NC}"
        echo "✓ PASSED: ${description}" >> "${TEST_LOG}"
        return 0
    else
        echo -e "${RED}✗ FAILED: ${description}${NC}"
        echo "✗ FAILED: ${description}" >> "${TEST_LOG}"
        return 1
    fi
}

###########################################
# SECTION 1: Environment and Dependencies
###########################################
print_section "Environment and Dependencies"

# Check Python version
run_test "Python version check" "python -c 'import sys; assert sys.version_info >= (3, 8), \"Python 3.8+ required\"'"

# Check pip dependencies
run_test "Check pip dependencies" "pip install -e . && pip check"

###########################################
# SECTION 2: Unit Tests
###########################################
print_section "Unit Tests"

# Run pytest for all unit tests
run_test "Core unit tests" "cd ${PROJECT_DIR} && python -m pytest tests/core/ -v"
run_test "Configuration unit tests" "cd ${PROJECT_DIR} && python -m pytest tests/core/test_configuration.py tests/core/test_apiconfig.py -v"
run_test "Monitoring unit tests" "cd ${PROJECT_DIR} && python -m pytest tests/monitoring/ -v"
run_test "Engines unit tests" "cd ${PROJECT_DIR} && python -m pytest tests/engines/test_chain_worker.py tests/engines/test_strategyexecutionerror.py -v"
run_test "Persistence unit tests" "cd ${PROJECT_DIR} && python -m pytest tests/persistence/ -v"
run_test "Integration unit tests" "cd ${PROJECT_DIR} && python -m pytest tests/integrations/ -v"
run_test "Utils unit tests" "cd ${PROJECT_DIR} && python -m pytest tests/utils/ -v"
run_test "CLI unit tests" "cd ${PROJECT_DIR} && python -m pytest tests/cli/ -v"

###########################################
# SECTION 3: Integration Tests
###########################################
print_section "Integration Tests"

# Run integration tests
run_test "Basic integration tests" "cd ${PROJECT_DIR} && python -m pytest tests/test_integration.py -v"

# Test database integration with real file-based SQLite (not in-memory)
run_test "Database integration tests" "cd ${PROJECT_DIR} && SQLALCHEMY_DATABASE_URL='sqlite:///./test_db.sqlite' python -m pytest tests/persistence/ -v"

# Clean up test database
rm -f "${PROJECT_DIR}/test_db.sqlite"

###########################################
# SECTION 4: Edge Case Tests
###########################################
print_section "Edge Case Tests"

# Run edge case tests if they exist
if [ -d "${PROJECT_DIR}/tests/edgecases" ]; then
    run_test "Edge case tests" "cd ${PROJECT_DIR} && python -m pytest tests/edgecases/ -v"
else
    echo "Edge case tests directory not found, skipping."
    echo "Edge case tests directory not found, skipping." >> "${TEST_LOG}"
fi

# Run the specific edge cases test script if it exists
if [ -f "${PROJECT_DIR}/run_edge_tests.sh" ]; then
    run_test "Run edge tests script" "cd ${PROJECT_DIR} && bash run_edge_tests.sh"
fi

###########################################
# SECTION 5: Configuration Testing
###########################################
print_section "Configuration Testing"

# Test that the configuration file is valid
run_test "Configuration validation" "cd ${PROJECT_DIR} && python -c 'from on1builder.config.config import Configuration; config = Configuration(); print(\"Configuration loaded successfully\")'"

# Test configuration file with skip_env=True
run_test "Configuration skip_env parameter" "cd ${PROJECT_DIR} && python -c 'from on1builder.config.config import Configuration; config = Configuration(skip_env=True); print(\"Configuration with skip_env=True loaded successfully\")'"

# Test configuration file with example path
run_test "Configuration with specific path" "cd ${PROJECT_DIR} && python -c 'from on1builder.config.config import Configuration; import os; config_path = os.path.join(\"configs\", \"chains\", \"example_config.yaml\"); config = Configuration(config_path=config_path, skip_env=True); print(\"Configuration with specific path loaded successfully\")'"

###########################################
# SECTION 6: Infrastructure Tests
###########################################
print_section "Infrastructure Testing"

# Check Docker Compose files
run_test "Docker Compose file validation (prod)" "cd ${PROJECT_DIR} && docker-compose -f docker/compose/docker-compose.prod.yml config"
run_test "Docker Compose file validation (multi-chain)" "cd ${PROJECT_DIR} && docker-compose -f docker/compose/docker-compose.multi-chain.yml config"

# Test shell scripts for errors (using shell check if available)
if command -v shellcheck >/dev/null 2>&1; then
    run_test "Shell script validation" "find ${PROJECT_DIR}/infra/bash -name '*.sh' -exec shellcheck {} \\;"
else
    echo "shellcheck not found, skipping shell script validation."
    echo "shellcheck not found, skipping shell script validation." >> "${TEST_LOG}"
fi

# Test if unified deploy script works
run_test "Unified deploy script help" "cd ${PROJECT_DIR} && bash infra/bash/deploy.sh --help || true"

# Test vault initialization script
run_test "Vault init script help" "cd ${PROJECT_DIR} && bash infra/bash/vault_init.sh --help || true"

###########################################
# SECTION 7: Code Quality Tests
###########################################
print_section "Code Quality Tests"

# Run flake8 if available
if command -v flake8 >/dev/null 2>&1; then
    run_test "Flake8 code style check" "cd ${PROJECT_DIR} && flake8 src/on1builder/"
else
    echo "flake8 not found, skipping code style check."
    echo "flake8 not found, skipping code style check." >> "${TEST_LOG}"
fi

# Run black if available
if command -v black >/dev/null 2>&1; then
    run_test "Black code formatter check" "cd ${PROJECT_DIR} && black --check src/on1builder/"
else
    echo "black not found, skipping code formatter check."
    echo "black not found, skipping code formatter check." >> "${TEST_LOG}"
fi

# Run isort if available
if command -v isort >/dev/null 2>&1; then
    run_test "isort import check" "cd ${PROJECT_DIR} && isort --check-only src/on1builder/"
else
    echo "isort not found, skipping import check."
    echo "isort not found, skipping import check." >> "${TEST_LOG}"
fi

# Run mypy if available
if command -v mypy >/dev/null 2>&1; then
    run_test "mypy type checker" "cd ${PROJECT_DIR} && mypy src/on1builder/"
else
    echo "mypy not found, skipping type check."
    echo "mypy not found, skipping type check." >> "${TEST_LOG}"
fi

###########################################
# SECTION 8: Security Tests
###########################################
print_section "Security Tests"

# Run bandit if available
if command -v bandit >/dev/null 2>&1; then
    run_test "Bandit security check" "cd ${PROJECT_DIR} && bandit -r src/on1builder/"
else
    echo "bandit not found, skipping security check."
    echo "bandit not found, skipping security check." >> "${TEST_LOG}"
fi

# Run the security audit script if it exists
if [ -f "${PROJECT_DIR}/infra/bash/security_audit.sh" ]; then
    run_test "Security audit script" "cd ${PROJECT_DIR} && bash infra/bash/security_audit.sh"
fi

###########################################
# SECTION 9: Test Coverage
###########################################
print_section "Test Coverage"

# Run coverage if available
if command -v coverage >/dev/null 2>&1; then
    run_test "Test coverage" "cd ${PROJECT_DIR} && coverage run -m pytest && coverage report"
else
    echo "coverage not found, skipping test coverage analysis."
    echo "coverage not found, skipping test coverage analysis." >> "${TEST_LOG}"
fi

###########################################
# SECTION 10: Summary
###########################################
print_section "Test Summary"

# Find the number of passed and failed tests
PASSED=$(grep -c "✓ PASSED:" "${TEST_LOG}")
FAILED=$(grep -c "✗ FAILED:" "${TEST_LOG}")
TOTAL=$((PASSED + FAILED))

echo -e "\n${YELLOW}Test Summary:${NC}"
echo -e "Total tests: ${TOTAL}"
echo -e "${GREEN}Passed: ${PASSED}${NC}"
echo -e "${RED}Failed: ${FAILED}${NC}"

echo -e "\nTest Summary:" >> "${TEST_LOG}"
echo "Total tests: ${TOTAL}" >> "${TEST_LOG}"
echo "Passed: ${PASSED}" >> "${TEST_LOG}"
echo "Failed: ${FAILED}" >> "${TEST_LOG}"
echo -e "\nTest completed at: $(date)" >> "${TEST_LOG}"

echo -e "\n${YELLOW}Comprehensive test log: ${TEST_LOG}${NC}"

# Exit with appropriate status code
if [ ${FAILED} -eq 0 ]; then
    echo -e "\n${GREEN}All tests passed successfully!${NC}"
    exit 0
else
    echo -e "\n${RED}Some tests failed. Please check the log for details.${NC}"
    exit 1
fi
