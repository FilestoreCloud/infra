import http from 'k6/http';
import { check, sleep } from 'k6';

// Control Plane API Burst and Concurrency Stress Test Suite
export const options = {
  stages: [
    { duration: '15s', target: 20 },
    { duration: '30s', target: 50 },
    { duration: '15s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<250', 'p(99)<500'],
    http_req_failed: ['rate<0.005'],
  },
};

const BASE_API = __ENV.API_URL || 'http://localhost:8080/api';
const ADMIN_TOKEN = __ENV.ADMIN_TOKEN || 'mock-admin-token';

export default function () {
  const headers = {
    'Content-Type': 'application/json',
    'X-Admin-Token': ADMIN_TOKEN,
  };

  // 1. Query Tenant Directory
  const resTenants = http.get(`${BASE_API}/tenants`, { headers });
  check(resTenants, {
    'Get Tenants status is 200': (r) => r.status === 200,
  });

  // 2. Query System Observability & Audit Logs
  const resAudit = http.get(`${BASE_API}/audit-logs?limit=25`, { headers });
  check(resAudit, {
    'Audit Logs status is 200': (r) => r.status === 200,
  });

  sleep(0.5);
}
