package local.campus.review.content;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.List;

public final class DocumentModels {
    private DocumentModels() {}
    @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
    public record Source(String sourceId,String url,String kind,String workId,String revisionId,String title) {
        public Source(String sourceId,String url){this(sourceId,url,null,null,null,null);}
    }
    public record DocumentInput(String title,String schemaVersion,JsonNode content,List<Source> sources) {}
    public record Position(String nodeId,int plainStart,int plainEnd,int nodeTextStart,int nodeTextEnd) {}
    public record ImageNode(String nodeId,String fileId,String caption,String origin,String sourceUrl) {}
    public record CitationSpan(String sourceId,String nodeId,int plainStart,int plainEnd) {}
    public record ExtractedDocument(DocumentInput document,String plainText,List<Position> positionMap,List<ImageNode> images,String contentHash,String schemaVersion,String extractorVersion,List<CitationSpan> citations) {}
}
