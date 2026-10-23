package ai.devproof.knowledge;

import java.util.concurrent.Semaphore;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** Coordinate the two durable queues against the same configured compute capacity. */
@Component
public class ComputeExecutionLane {
    private final Semaphore permits;
    public ComputeExecutionLane(@Value("${COMPUTE_CONCURRENCY:1}") int concurrency) {
        if(concurrency<1 || concurrency>8)throw new IllegalArgumentException("Invalid compute concurrency");
        permits=new Semaphore(concurrency);
    }
    public boolean acquire() { return permits.tryAcquire(); }
    public void release() { permits.release(); }
}
