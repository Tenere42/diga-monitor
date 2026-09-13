from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor

from poc.http_signup.rate_limit import InMemoryRateLimiter


class InMemoryRateLimiterTests(unittest.TestCase):
    def test_allows_up_to_the_limit(self) -> None:
        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
        results = [limiter.allow("1.2.3.4", now=0.0) for _ in range(3)]
        self.assertEqual(results, [True, True, True])

    def test_rejects_beyond_the_limit_within_the_window(self) -> None:
        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
        self.assertTrue(limiter.allow("1.2.3.4", now=0.0))
        self.assertTrue(limiter.allow("1.2.3.4", now=1.0))
        self.assertFalse(limiter.allow("1.2.3.4", now=2.0))

    def test_allows_again_once_the_window_rolls_past_old_hits(self) -> None:
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=10)
        self.assertTrue(limiter.allow("1.2.3.4", now=0.0))
        self.assertFalse(limiter.allow("1.2.3.4", now=5.0))
        self.assertTrue(limiter.allow("1.2.3.4", now=10.1))

    def test_different_keys_are_tracked_independently(self) -> None:
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        self.assertTrue(limiter.allow("1.2.3.4", now=0.0))
        self.assertTrue(limiter.allow("5.6.7.8", now=0.0))
        self.assertFalse(limiter.allow("1.2.3.4", now=1.0))

    def test_rejected_calls_do_not_themselves_count_as_hits(self) -> None:
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=10)
        self.assertTrue(limiter.allow("1.2.3.4", now=0.0))
        self.assertFalse(limiter.allow("1.2.3.4", now=1.0))
        self.assertFalse(limiter.allow("1.2.3.4", now=2.0))
        # No matter how many times it's rejected, the window still rolls
        # off only the original hit at t=0.
        self.assertTrue(limiter.allow("1.2.3.4", now=10.1))

    def test_thread_safety_never_allows_more_than_the_limit_under_concurrency(self) -> None:
        # Substantiates the docstring/Lock claim: fire far more concurrent
        # callers than the limit allows and confirm the *count* of
        # successes never exceeds it, however the OS happens to schedule
        # the threads. Real (not mocked) time is used here deliberately,
        # since the point is to catch a genuine race condition -- a fixed
        # `now` would serialize nothing and prove nothing about locking.
        limiter = InMemoryRateLimiter(max_requests=10, window_seconds=60)
        with ThreadPoolExecutor(max_workers=50) as pool:
            results = list(pool.map(lambda _: limiter.allow("shared-key"), range(200)))
        self.assertEqual(sum(1 for allowed in results if allowed), 10)

    def test_rejects_invalid_construction_arguments(self) -> None:
        with self.assertRaises(ValueError):
            InMemoryRateLimiter(max_requests=0, window_seconds=60)
        with self.assertRaises(ValueError):
            InMemoryRateLimiter(max_requests=1, window_seconds=0)


if __name__ == "__main__":
    unittest.main()
