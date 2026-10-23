package local.campus.review.detection;
import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.common.RuntimeSettings;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
class DetectorBudgetTest {
    @Test void httpTimeoutDoesNotMeanRemoteComputeFinished()throws Exception{
        var busy=new java.util.concurrent.atomic.AtomicBoolean();var executor=java.util.concurrent.Executors.newCachedThreadPool();
        var server=com.sun.net.httpserver.HttpServer.create(new java.net.InetSocketAddress("127.0.0.1",0),0);server.setExecutor(executor);
        server.createContext("/detect/text",exchange->{busy.set(true);try{Thread.sleep(1800);byte[] body="{}".getBytes();exchange.sendResponseHeaders(200,body.length);exchange.getResponseBody().write(body);}catch(Exception ignored){}finally{busy.set(false);exchange.close();}});
        server.createContext("/health",exchange->{byte[] body=("{\"ready\":true,\"runId\":\"controlled-timeout-test\",\"busy\":"+busy.get()+"}").getBytes();exchange.sendResponseHeaders(200,body.length);exchange.getResponseBody().write(body);exchange.close();});server.start();
        try{
            var settings=mock(RuntimeSettings.class);when(settings.root()).thenReturn(java.nio.file.Path.of(System.getenv("CAMPUS_ROOT")));when(settings.port("detector")).thenReturn(server.getAddress().getPort());when(settings.timeout("text")).thenReturn(1);
            var client=new DetectorClient(settings,new ObjectMapper());var failure=assertThrows(DetectorClient.DetectorFailure.class,()->client.call(false,"/detect/text",new ObjectMapper().createObjectNode(),"text"));
            assertEquals("DETECTOR_TIMEOUT",failure.code);assertTrue(client.health(false).path("busy").asBoolean());
        }finally{server.stop(0);executor.shutdownNow();}
    }
    @Test void combinedOcrBudgetExpiresBeforeAnotherRequest()throws Exception{
        var settings=mock(RuntimeSettings.class);when(settings.timeout("ocrAndText")).thenReturn(1);
        var client=new DetectorClient(settings,new ObjectMapper());
        try(var budget=client.budget("ocrAndText")){
            Thread.sleep(1100);
            var failure=assertThrows(DetectorClient.DetectorFailure.class,()->client.call(false,"/detect/text",new ObjectMapper().createObjectNode(),"ocrAndText"));
            assertEquals("DETECTOR_TIMEOUT",failure.code);
        }
        verify(settings,never()).port(anyString());
    }
}
