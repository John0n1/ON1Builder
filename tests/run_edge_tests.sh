#!/bin/bash
# Script to run the edge case tests with proper Python path

set -e

echo "Running edge case tests..."
cd /home/john0n1/ON1Builder-1
export PYTHONPATH=/home/john0n1/ON1Builder-1:/home/john0n1/ON1Builder-1/src
python -m pytest tests/edgecases/ -v

echo "Tests completed"
