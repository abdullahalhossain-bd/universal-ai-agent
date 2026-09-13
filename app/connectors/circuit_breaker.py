import time


class CircuitBreaker:

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_time_seconds: int = 30,
    ):

        self.failure_threshold = failure_threshold
        self.recovery_time_seconds = recovery_time_seconds

        self.failure_count = 0
        self.state = "CLOSED"
        self.opened_at = None

    def record_success(self):

        self.failure_count = 0
        self.state = "CLOSED"
        self.opened_at = None

    def record_failure(self):

        self.failure_count += 1

        if self.failure_count >= self.failure_threshold:

            self.state = "OPEN"
            self.opened_at = time.time()

    def allow_request(self):

        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":

            if (
                self.opened_at is not None
                and time.time() - self.opened_at
                > self.recovery_time_seconds
            ):

                self.state = "HALF_OPEN"

                return True

            return False

        if self.state == "HALF_OPEN":
            return True

        return False
