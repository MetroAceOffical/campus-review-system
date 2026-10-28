package local.campus.review.workbench;

import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.auth.CurrentUser;
import local.campus.review.common.ApiException;
import org.junit.jupiter.api.Test;
import java.nio.file.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class FormalTrainingServiceTest {
    private final ObjectMapper json=new ObjectMapper();

    @Test void creatorCannotReadFormalProgress() {
        var data=new DatasetService(null,null,json,new org.springframework.jdbc.datasource.DataSourceTransactionManager());
        var actor=new CurrentUser("1","创作者",CurrentUser.Role.MEMBER,Set.of(),List.of());
        assertEquals("ACCESS_DENIED",assertThrows(ApiException.class,()->new FormalTrainingService(data).progress(actor)).code);
    }

    @Test void readsActualCountsAndBoundedHistoryWithoutNewsOrOutsidePaths() throws Exception {
        Path parent=Path.of("../../runtime").toAbsolutePath().normalize();
        Path root=Files.createTempDirectory(parent,"formal-progress-test-");
        try {
            Path runtime=root.resolve("runtime"),folder=runtime.resolve("experiments/test");Files.createDirectories(folder);
            Path registry=root.resolve("app/config/formal-pipeline.json");Files.createDirectories(registry.getParent());
            Files.writeString(registry,"""
                {"schemaVersion":1,"title":"正式训练","stages":[
                  {"key":"generation","title":"样本准备","directory":"runtime/experiments/test","historyFile":"history.jsonl"},
                  {"key":"pending","title":"待训练","directory":"runtime/experiments/missing"},
                  {"key":"escape","title":"错误路径","directory":"../outside"}]}
                """);
            Files.writeString(folder.resolve("status.json"),"""
                {"state":"GENERATING_TRAIN_MATERIAL","segmentCounts":{"ACCEPTED":12,"PENDING":7,"QUARANTINED":1},"selectedOriginals":8,"text":"原稿不能进入接口","path":"private-config/secret"}
                """);
            Files.writeString(folder.resolve("history.jsonl"),"{\"step\":1,\"loss\":0.5,\"sourceText\":\"隐藏新闻\"}\n{\"step\":2,\"loss\":0.4}\n{broken");
            var result=FormalTrainingService.read(root,runtime,json,registry);
            var stage=result.path("stages").get(0);
            assertEquals(13,stage.path("progress").path("processed").asInt());assertEquals(20,stage.path("progress").path("total").asInt());
            assertEquals(12,stage.path("metrics").path("accepted").asInt());assertEquals(2,stage.path("history").size());
            Files.setLastModifiedTime(folder.resolve("status.json"),java.nio.file.attribute.FileTime.from(java.time.Instant.now().minusSeconds(1000)));
            assertTrue(FormalTrainingService.read(root,runtime,json,registry).path("stages").get(0).path("stale").asBoolean());
            assertEquals("PENDING",result.path("stages").get(1).path("availability").asText());
            assertEquals("READ_ERROR",result.path("stages").get(2).path("availability").asText());
            assertFalse(result.toString().contains("隐藏新闻"));assertFalse(result.toString().contains("private-config"));assertFalse(result.toString().contains("outside"));
            var history=new StringBuilder();for(int index=0;index<600;index++)history.append("{\"step\":").append(index).append(",\"loss\":0.5}\n");history.append("{writing");
            Files.writeString(folder.resolve("history.jsonl"),history);
            var bounded=FormalTrainingService.read(root,runtime,json,registry).path("stages").get(0).path("history");
            assertEquals(500,bounded.size());assertEquals(100,bounded.get(0).path("step").asInt());
            Files.writeString(folder.resolve("status.json"),"{\"state\":\"TRAIN_CONSTRUCTION_FINISHED\",\"counts\":{\"ACCEPTED\":12}}");
            var finished=FormalTrainingService.read(root,runtime,json,registry).path("stages").get(0);
            assertEquals(0,finished.path("metrics").path("pending").asInt(-1));assertEquals(100,finished.path("progress").path("percent").asDouble());
            Files.writeString(folder.resolve("status.json"),"""
                {"state":"RUNNING_IMAGE_DEVELOPMENT_EVALUATION","processed":3,"total":1064,
                 "baselineAccepted":2,"top20Accepted":3,"enhancedAccepted":1,"scopeCorrect":1,
                 "dinoTop20Retrieved":3,"failedQueries":1,"unknownAcceptedSources":2,
                 "finalQueriesEvaluated":0,"realHardNegativeTruthCount":0,"privatePath":"hidden"}
                """);
            var evaluation=FormalTrainingService.read(root,runtime,json,registry).path("stages").get(0);
            assertEquals(3,evaluation.path("progress").path("processed").asInt());
            assertEquals(1,evaluation.path("metrics").path("enhancedAccepted").asInt(-1));
            assertEquals(1,evaluation.path("metrics").path("failedQueries").asInt(-1));
            assertFalse(evaluation.toString().contains("privatePath"));
            Files.writeString(folder.resolve("status.json"),"{writing");
            var changed=FormalTrainingService.read(root,runtime,json,registry);
            assertEquals("READ_ERROR",changed.path("stages").get(0).path("availability").asText());
        } finally {
            try(var entries=Files.walk(root)){for(var path:entries.sorted(Comparator.reverseOrder()).toList())Files.deleteIfExists(path);}
        }
    }

    @Test void actualRegisteredPipelineReadsWithoutChangingArtifacts() throws Exception {
        Path root=Path.of("../..").toAbsolutePath().normalize(),registry=root.resolve("app/config/formal-pipeline.json");
        org.junit.jupiter.api.Assumptions.assumeTrue(Files.isRegularFile(registry));
        var result=FormalTrainingService.read(root,root.resolve("runtime"),json,registry);
        assertTrue(result.path("configured").asBoolean());assertEquals(3684,result.path("recipe").path("generationOriginals").asInt());
        assertEquals(16773,result.path("recipe").path("generationSegments").asInt());assertEquals(2,result.path("recipe").path("epochsBge").asInt());
        assertEquals(json.readTree(Files.readString(registry)).path("stages").size(),result.path("stages").size());
        assertFalse(result.toString().contains("private-config"));assertFalse(result.toString().contains("sourceText"));
        Files.writeString(root.resolve("runtime/workbench-implementation/stage13-formal-progress-sample.json"),json.writerWithDefaultPrettyPrinter().writeValueAsString(result));
    }
}
