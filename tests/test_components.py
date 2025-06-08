#!/usr/bin/env python3
"""
Test component creation and integration.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_config_loading():
    """Test configuration loading with different settings."""
    print("📋 Testing configuration loading...")
    
    try:
        from on1builder.config.loaders import ConfigLoader
        
        # Test config loader
        loader = ConfigLoader()
        
        # Test with actual config file
        config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'common_settings.yaml')
        if os.path.exists(config_path):
            global_settings = loader.load_global_config()
            print(f"✅ Global settings loaded: {type(global_settings).__name__}")
            print(f"   Debug: {global_settings.debug}")
            print(f"   Database URL: {global_settings.database_url}")
        
        # Test with chain configs
        chains_dir = os.path.join(os.path.dirname(__file__), '..', 'configs', 'chains')
        if os.path.exists(chains_dir):
            config_files = [f for f in os.listdir(chains_dir) if f.endswith('.yaml')]
            if config_files:
                multi_chain_settings = loader.load_multi_chain_config()
                print(f"✅ Multi-chain settings loaded: {len(multi_chain_settings.chains)} chains")
        
        assert True, "Configuration loading successful"
        
    except Exception as e:
        print(f"❌ Configuration loading failed: {e}")
        assert False, f"Configuration loading failed: {e}"

def test_database_interface():
    """Test database interface creation."""
    print("📋 Testing database interface...")
    
    try:
        from on1builder.config.loaders import ConfigLoader
        from on1builder.persistence import DatabaseInterface, DatabaseManager
        
        # Load config
        loader = ConfigLoader()
        config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'common_settings.yaml')
        if os.path.exists(config_path):
            global_settings = loader.load_global_config()
        else:
            from on1builder.config.settings import GlobalSettings
            global_settings = GlobalSettings()
        
        # Test DatabaseInterface
        db = DatabaseInterface(global_settings)
        print(f"✅ DatabaseInterface created: {type(db).__name__}")
        print(f"   Connection check: {db.check_connection()}")
        
        # Test type alias
        db2 = DatabaseManager(global_settings)
        print(f"✅ DatabaseManager (alias) created: {type(db2).__name__}")
        
        assert True, "Database interface test successful"
        
    except Exception as e:
        print(f"❌ Database interface test failed: {e}")
        assert False, f"Database interface test failed: {e}"

def test_main_orchestrator():
    """Test MainOrchestrator creation."""
    print("📋 Testing MainOrchestrator...")
    
    try:
        from on1builder.config.loaders import ConfigLoader
        from on1builder.core.main_orchestrator import MainOrchestrator
        
        # Load configs
        loader = ConfigLoader()
        config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'common_settings.yaml')
        chains_dir = os.path.join(os.path.dirname(__file__), '..', 'configs', 'chains')
        
        if os.path.exists(config_path):
            global_settings = loader.load_global_config()
        else:
            from on1builder.config.settings import GlobalSettings
            global_settings = GlobalSettings()
        
        # Test MainOrchestrator creation (it takes a single config parameter)
        orchestrator = MainOrchestrator(global_settings)
        print(f"✅ MainOrchestrator created: {type(orchestrator).__name__}")
        
        assert True, "MainOrchestrator test successful"
        
    except Exception as e:
        print(f"❌ MainOrchestrator test failed: {e}")
        import traceback
        traceback.print_exc()
        assert False, f"MainOrchestrator test failed: {e}"

def test_abi_registry():
    """Test ABI registry functionality."""
    print("📋 Testing ABI registry...")
    
    try:
        from on1builder.integrations.abi_registry import ABIRegistry
        
        # Test creation
        registry = ABIRegistry()
        print(f"✅ ABIRegistry created: {type(registry).__name__}")
        
        # Test getting a common ABI
        erc20_abi = registry.get_abi('erc20')
        if erc20_abi:
            print(f"✅ ERC20 ABI loaded: {len(erc20_abi)} functions")
        
        assert True, "ABI registry test successful"
        
    except Exception as e:
        print(f"❌ ABI registry test failed: {e}")
        assert False, f"ABI registry test failed: {e}"

def main():
    """Run all component tests."""
    print("🚀 Testing ON1Builder component integration...")
    print("=" * 50)
    
    tests = [
        test_config_loading,
        test_database_interface,
        test_abi_registry,
        test_main_orchestrator,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        print()
        if test():
            passed += 1
        print("-" * 30)
    
    print()
    print("=" * 50)
    print(f"📊 Test Results:")
    print(f"✅ Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All component tests passed!")
        return True
    else:
        print(f"❌ {total - passed} tests failed.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
