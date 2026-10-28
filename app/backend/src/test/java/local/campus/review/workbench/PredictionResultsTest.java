package local.campus.review.workbench;

import com.fasterxml.jackson.databind.*;
import local.campus.review.auth.CurrentUser;
import local.campus.review.common.ApiException;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class PredictionResultsTest {
    private final ObjectMapper json=new ObjectMapper();
    private Path temporary()throws Exception{return Files.createTempDirectory(Path.of("../../runtime").toAbsolutePath().normalize(),"prediction-results-test-");}
    private void clean(Path folder)throws Exception{try(var files=Files.walk(folder)){for(var file:files.sorted(Comparator.reverseOrder()).toList())Files.deleteIfExists(file);}}
    private String sha(Path path)throws Exception{try(var stream=Files.newInputStream(path)){return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(stream.readAllBytes()));}}
    private JsonNode manifest(Path file,long rows)throws Exception{return json.createObjectNode().put("status","COMPLETED").put("taskType","PREDICTION").put("count",rows).set("artifacts",json.createObjectNode().put("predictions.jsonl",sha(file)));}

    @Test void fullResultPagesCombineTextClassAndErrorFilters()throws Exception{
        Path folder=temporary();try{
            Path file=folder.resolve("predictions.jsonl");var lines=new StringBuilder();
            for(int i=0;i<55;i++)lines.append("{\"id\":\"").append(i).append("\",\"sentence1\":\"新闻").append(i).append("\",\"sentence2\":\"活动报道\",\"score\":0.7,\"predicted\":").append(i%2).append(",\"label\":").append(i%3==0?1:0).append(",\"scoreType\":\"probability\"}\n");
            Files.writeString(file,lines);var frozen=manifest(file,55);
            var second=TrainingService.predictionPage(json,file,frozen,2,20,"",null,"all");
            assertEquals(55,second.path("count").asInt());assertEquals(55,second.path("total").asInt());assertEquals(20,second.path("items").size());assertEquals("20",second.path("items").get(0).path("id").asText());
            var errors=TrainingService.predictionPage(json,file,frozen,1,100,"活动",1,"FP");
            assertEquals(18,errors.path("total").asInt());for(var row:errors.path("items")){assertEquals("FP",row.path("outcome").asText());assertEquals(0,row.path("label").asInt());assertEquals(1,row.path("predicted").asInt());}
            assertEquals(0,TrainingService.predictionPage(json,file,frozen,1,20,"不存在",null,"all").path("total").asInt());
        }finally{clean(folder);}
    }
    @Test void invalidFiltersChangedBytesAndUnfinishedRowsAreRejected()throws Exception{
        Path folder=temporary();try{
            Path file=folder.resolve("predictions.jsonl");Files.writeString(file,"{\"sentence1\":\"甲\",\"sentence2\":\"乙\",\"score\":-0.1,\"predicted\":0,\"scoreType\":\"margin\"}\n");var frozen=manifest(file,1);
            assertEquals(400,assertThrows(ApiException.class,()->TrainingService.predictionPage(json,file,frozen,0,20,"",null,"all")).status);
            assertEquals(400,assertThrows(ApiException.class,()->TrainingService.predictionPage(json,file,frozen,1,101,"",null,"all")).status);
            assertEquals(400,assertThrows(ApiException.class,()->TrainingService.predictionPage(json,file,frozen,1,20,"",2,"all")).status);
            assertEquals(0,TrainingService.predictionPage(json,file,frozen,1,20,"",null,"FP").path("total").asInt());
            Files.writeString(file,Files.readString(file).replace("-0.1","-0.2"));assertEquals("ARTIFACT_CHANGED",assertThrows(ApiException.class,()->TrainingService.predictionPage(json,file,frozen,1,20,"",null,"all")).code);
            Files.writeString(file,"{writing");var broken=manifest(file,1);assertEquals("ARTIFACT_CHANGED",assertThrows(ApiException.class,()->TrainingService.predictionPage(json,file,broken,1,20,"",null,"all")).code);
        }finally{clean(folder);}
    }
    @Test void uploadedFilesKeepMetadataAndBytesWhileCreatorsAreDenied()throws Exception{
        var data=new DatasetService(null,null,json,new org.springframework.jdbc.datasource.DataSourceTransactionManager());var service=new TrainingService(data);
        var creator=new CurrentUser("1","创作者",CurrentUser.Role.MEMBER,Set.of(),List.of());
        var source=new MockMultipartFile("file","C:\\fakepath\\预测.CSV","text/csv","文本一,文本二\n甲,乙\n".getBytes(StandardCharsets.UTF_8));
        assertEquals("ACCESS_DENIED",assertThrows(ApiException.class,()->service.predictFile(creator,UUID.randomUUID().toString(),source)).code);
        Path folder=temporary();try{
            var descriptor=TrainingService.storePredictionInput(json,source,folder);
            assertEquals("csv",descriptor.path("format").asText());assertEquals("预测.CSV",descriptor.path("name").asText());assertEquals(sha(folder.resolve("prediction-source.csv")),descriptor.path("sha256").asText());assertFalse(descriptor.has("path"));
            byte[] before=Files.readAllBytes(folder.resolve("prediction-source.csv"));assertThrows(FileAlreadyExistsException.class,()->TrainingService.storePredictionInput(json,source,folder));assertArrayEquals(before,Files.readAllBytes(folder.resolve("prediction-source.csv")));
            assertEquals(415,assertThrows(ApiException.class,()->TrainingService.storePredictionInput(json,new MockMultipartFile("file","invalid.exe","text/plain",new byte[]{1}),folder)).status);
        }finally{clean(folder);}
    }
    @Test void actualSavedEvaluationCanReadAll4487RowsAndFalsePositives()throws Exception{
        Path folder=Path.of("../../runtime/workbench/computations/3070c539-d8ca-46d9-96d4-9dfcd49039fa/output").toAbsolutePath().normalize();
        org.junit.jupiter.api.Assumptions.assumeTrue(Files.isRegularFile(folder.resolve("manifest.json")));
        var frozen=json.readTree(Files.readString(folder.resolve("manifest.json")));Path file=folder.resolve("predictions.jsonl");
        var first=TrainingService.predictionPage(json,file,frozen,1,20,"",null,"all");var second=TrainingService.predictionPage(json,file,frozen,2,20,"",null,"all");var errors=TrainingService.predictionPage(json,file,frozen,1,100,"",null,"FP");
        assertEquals(4487,first.path("count").asInt());assertEquals(4487,second.path("total").asInt());assertEquals(20,first.path("items").size());assertEquals(20,second.path("items").size());assertNotEquals(first.path("items").get(0).path("id"),second.path("items").get(0).path("id"));
        long actual=0;try(var reader=Files.newBufferedReader(file)){String line;while((line=reader.readLine())!=null){var row=json.readTree(line);if(row.path("label").asInt()==0&&row.path("predicted").asInt()==1)actual++;}}
        assertEquals(actual,errors.path("total").asLong());
        Files.writeString(Path.of("../../runtime/workbench-implementation/stage14-prediction-read-summary.json"),json.writerWithDefaultPrettyPrinter().writeValueAsString(json.createObjectNode().put("rows",4487).put("firstPageRows",20).put("secondPageRows",20).put("falsePositives",actual).put("artifactSha256",sha(file)).put("newTrainingOrGradeProduced",false)));
    }
}
