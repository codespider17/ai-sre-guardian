import http from 'k6/http';
import { check } from 'k6';

const baseUrl = __ENV.BASE_URL;
const capacityToken = __ENV.CAPACITY_TOKEN;

export function setup() {
  if (!baseUrl || !capacityToken) {
    throw new Error('BASE_URL and CAPACITY_TOKEN are required');
  }
}

export const options = {
  scenarios: {
    capacity_baseline: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '20s', target: 5 },
        { duration: '70s', target: 20 },
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '10s',
    },
  },
  thresholds: {
    checks: ['rate>0.98'],
    http_req_failed: ['rate<0.02'],
    http_req_duration: ['p(95)<1500'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)'],
};

const payload = JSON.stringify({ iterations: 50000, seed: 7 });
const requestParameters = {
  headers: {
    'Content-Type': 'application/json',
    'X-Capacity-Lab-Token': capacityToken,
  },
  tags: { endpoint: 'capacity-work' },
};

export default function () {
  const response = http.post(
    `${baseUrl}/api/v1/capacity-lab/work`,
    payload,
    requestParameters,
  );
  check(response, {
    'capacity endpoint returns 200': (result) => result.status === 200,
    'capacity response contains checksum': (result) => {
      if (result.status !== 200) {
        return false;
      }
      return result.json('checksum') === 1277304242;
    },
  });
}

export function handleSummary(data) {
  return {
    '/results/k6-summary.json': JSON.stringify(data, null, 2),
  };
}
