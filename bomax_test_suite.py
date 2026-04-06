"""
OrQuanta Enterprise Test Suite
Validates the full business lifecycle: Auth -> Billing -> Jobs -> Monitoring
"""

import asyncio
import aiohttp
import json
import logging
import secrets
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("OrQuanta-Test")

BASE_URL = "http://localhost:8000"
API_PREFIX = "/api/v1"

class OrQuantaTester:
    def __init__(self):
        self.session = None
        self.api_key = None
        self.user_email = f"test_{secrets.token_hex(4)}@orquanta.com"
        self.password = "secure_test_pass_123"
        self.passed = 0
        self.failed = 0
        
    async def run(self):
        logger.info("🚀 Starting OrQuanta Enterprise Validation...")
        
        async with aiohttp.ClientSession() as self.session:
            # 1. Platform Health
            await self.test_health()
            
            # 2. Authentication Flow
            await self.test_registration()
            await self.test_login()
            await self.test_get_me()
            
            # 3. Billing Flow
            await self.test_billing_status()
            await self.test_add_credits()
            
            # 4. Job Management Flow
            await self.test_pricing()
            job_id = await self.test_create_job()
            if job_id:
                await self.test_get_job(job_id)
                await self.test_list_jobs()
                await self.test_cancel_job(job_id)
                
            # 5. System Monitoring
            await self.test_system_metrics()
            
        self.print_summary()

    async def test_health(self):
        try:
            async with self.session.get(f"{BASE_URL}/health") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["platform"] == "OrQuanta"
                logger.info("✅ Platform Health: OK")
                self.passed += 1
        except Exception as e:
            logger.error(f"❌ Platform Health Failed: {e}")
            self.failed += 1

    async def test_registration(self):
        try:
            payload = {
                "email": self.user_email,
                "password": self.password,
                "full_name": "Test User",
                "company": "OrQuanta Validation Corp"
            }
            async with self.session.post(f"{BASE_URL}{API_PREFIX}/auth/register", json=payload) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["email"] == self.user_email
                # Automatically captures API key if returned, but usually login is needed
                if "api_key" in data:
                    self.api_key = data["api_key"]
                logger.info("✅ User Registration: OK")
                self.passed += 1
        except Exception as e:
            logger.error(f"❌ Registration Failed: {e}")
            self.failed += 1

    async def test_login(self):
        try:
            payload = {"email": self.user_email, "password": self.password}
            async with self.session.post(f"{BASE_URL}{API_PREFIX}/auth/login", json=payload) as resp:
                assert resp.status == 200
                data = await resp.json()
                self.api_key = data["api_key"]
                assert self.api_key is not None
                logger.info("✅ Login & API Key Retrieval: OK")
                self.passed += 1
        except Exception as e:
            logger.error(f"❌ Login Failed: {e}")
            self.failed += 1

    async def test_get_me(self):
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with self.session.get(f"{BASE_URL}{API_PREFIX}/auth/me", headers=headers) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["email"] == self.user_email
                logger.info("✅ User Profile Retrieval: OK")
                self.passed += 1
        except Exception as e:
            logger.error(f"❌ Profile Retrieval Failed: {e}")
            self.failed += 1

    async def test_billing_status(self):
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with self.session.get(f"{BASE_URL}{API_PREFIX}/billing", headers=headers) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert "current_balance" in data
                logger.info(f"✅ Billing Status Check (Balance: ${data['current_balance']}): OK")
                self.passed += 1
        except Exception as e:
            logger.error(f"❌ Billing Check Failed: {e}")
            self.failed += 1

    async def test_add_credits(self):
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            # Adding credits via query param as per typical simpler implementations or modify to json if needed
            # Based on code verification, it seems to expect query param 'amount'
            async with self.session.post(f"{BASE_URL}{API_PREFIX}/billing/add-credits?amount=500", headers=headers) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["new_balance"] >= 500
                logger.info("✅ Credit Top-up ($500): OK")
                self.passed += 1
        except Exception as e:
            logger.error(f"❌ Credit Top-up Failed: {e}")
            self.failed += 1

    async def test_pricing(self):
        try:
            async with self.session.get(f"{BASE_URL}{API_PREFIX}/pricing") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert "A100" in data["pricing"]
                logger.info("✅ Pricing Data Retrieval: OK")
                self.passed += 1
        except Exception as e:
            logger.error(f"❌ Pricing Check Failed: {e}")
            self.failed += 1

    async def test_create_job(self):
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            payload = {
                "gpu_type": "A100",
                "gpu_count": 1,
                "duration_hours": 2,
                "spot_instance": True # Test the cheaper option
            }
            async with self.session.post(f"{BASE_URL}{API_PREFIX}/jobs", json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Job Creation Error: {text}")
                assert resp.status == 200
                data = await resp.json()
                job_id = data["job_id"]
                logger.info(f"✅ Job Creation (ID: {job_id}): OK")
                self.passed += 1
                return job_id
        except Exception as e:
            logger.error(f"❌ Job Creation Failed: {e}")
            self.failed += 1
            return None

    async def test_get_job(self, job_id):
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with self.session.get(f"{BASE_URL}{API_PREFIX}/jobs/{job_id}", headers=headers) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert data["job_id"] == job_id
                logger.info("✅ Job Details Retrieval: OK")
                self.passed += 1
        except Exception as e:
            logger.error(f"❌ Job Details Failed: {e}")
            self.failed += 1

    async def test_list_jobs(self):
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with self.session.get(f"{BASE_URL}{API_PREFIX}/jobs", headers=headers) as resp:
                assert resp.status == 200
                data = await resp.json()
                assert len(data["jobs"]) > 0
                logger.info("✅ Job Listing: OK")
                self.passed += 1
        except Exception as e:
            logger.error(f"❌ Job Listing Failed: {e}")
            self.failed += 1

    async def test_cancel_job(self, job_id):
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with self.session.delete(f"{BASE_URL}{API_PREFIX}/jobs/{job_id}", headers=headers) as resp:
                assert resp.status == 200
                logger.info("✅ Job Cancellation: OK")
                self.passed += 1
        except Exception as e:
            logger.error(f"❌ Job Cancellation Failed: {e}")
            self.failed += 1

    async def test_system_metrics(self):
        try:
            async with self.session.get(f"{BASE_URL}{API_PREFIX}/metrics/system") as resp:
                assert resp.status == 200
                data = await resp.json()
                assert "gpu_utilization" in data
                logger.info("✅ System Metrics Monitoring: OK")
                self.passed += 1
        except Exception as e:
            logger.error(f"❌ System Metrics Failed: {e}")
            self.failed += 1

    def print_summary(self):
        print("\n" + "="*50)
        print("          ORQUANTA VALIDATION SUMMARY          ")
        print("="*50)
        print(f"Total Tests: {self.passed + self.failed}")
        print(f"Passed:      {self.passed} ✅")
        print(f"Failed:      {self.failed} ❌")
        print("="*50)
        if self.failed == 0:
            print("🚀 STATUS: READY FOR PRODUCTION LAUNCH")
        else:
            print("⚠️ STATUS: INVESTIGATION REQUIRED")

if __name__ == "__main__":
    runner = OrQuantaTester()
    asyncio.run(runner.run())
