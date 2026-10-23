package local.campus.review.detection;

import org.springframework.stereotype.Component;

/** Readiness proof only. OS handles are managed by the project launcher, never by guessed PIDs. */
@Component
public class ProcessSupervisor {
    private final DetectorClient client;
    public ProcessSupervisor(DetectorClient client){this.client=client;}
    public boolean ensureReady(boolean ocr){var health=client.health(ocr);return health.path("ready").asBoolean()&&!health.path("busy").asBoolean()&&!health.path("runId").asText().isBlank();}
}
