#!/usr/bin/env python3
"""
Basic test to verify ON1Builder package structure after migration.
"""

import sys
from pathlib import Path

def test_imports():
    """Test that basic imports work."""
    try:
        # Test main package
        import on1builder
        print("✅ on1builder package imports successfully")
        
        # Test config module
        from on1builder.config import settings, loaders
        print("✅ config module imports successfully")
        
        # Test utils
        from on1builder.utils import logging_config, path_helpers
        print("✅ utils module imports successfully")
        
        # Test integrations
        from on1builder.integrations import abi_registry
        print("✅ integrations module imports successfully")
        
        # Test CLI
        from on1builder.cli import config_cmd, run_cmd, status_cmd
        print("✅ CLI modules import successfully")
        
        # Test that path helpers work
        resource_path = path_helpers.get_resource_path("abi", "erc20_abi.json")
        print(f"✅ Resource path helper works: {resource_path}")
        
        assert True, "All imports successful"
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        assert False, f"Import error: {e}"
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        assert False, f"Unexpected error: {e}"

def test_cli_entry_point():
    """Test that the CLI entry point works."""
    try:
        from on1builder.__main__ import app
        print("✅ CLI entry point imports successfully")
        assert True, "CLI entry point test successful"
    except ImportError as e:
        print(f"❌ CLI import error: {e}")
        assert False, f"CLI import error: {e}"

def test_resource_files():
    """Test that resource files are accessible."""
    try:
        from on1builder.utils.path_helpers import get_abi_path, get_token_data_path, get_strategy_weights_path
        
        abi_path = get_abi_path("erc20_abi.json")
        tokens_path = get_token_data_path()
        ml_path = get_strategy_weights_path()
        
        print(f"✅ ABI path: {abi_path} (exists: {abi_path.exists()})")
        print(f"✅ Tokens path: {tokens_path} (exists: {tokens_path.exists()})")
        print(f"✅ ML models path: {ml_path} (exists: {ml_path.exists()})")
        
        assert True, "Resource files test successful"
    except Exception as e:
        print(f"❌ Resource test error: {e}")
        assert False, f"Resource test error: {e}"

def main():
    """Run all tests."""
    print("🚀 Testing ON1Builder package structure...")
    print("-" * 50)
    
    tests = [
        test_imports,
        test_cli_entry_point,
        test_resource_files
    ]
    
    results = []
    for test in tests:
        print(f"\n📋 Running {test.__name__}...")
        results.append(test())
    
    print("\n" + "=" * 50)
    print("📊 Test Results:")
    passed = sum(results)
    total = len(results)
    
    print(f"✅ Passed: {passed}/{total}")
    if passed == total:
        print("🎉 All tests passed! Package structure is working.")
        return 0
    else:
        print("❌ Some tests failed. Please check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
