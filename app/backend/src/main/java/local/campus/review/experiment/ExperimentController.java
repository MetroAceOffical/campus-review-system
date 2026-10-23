package local.campus.review.experiment;

import local.campus.review.common.Api;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/experiments")
public class ExperimentController {
    private final ExperimentCatalog catalog;
    public ExperimentController(ExperimentCatalog catalog){this.catalog=catalog;}
    @GetMapping Api list(){return Api.ok(catalog.list());}
    @GetMapping("/{id}") Api manifest(@PathVariable String id){return Api.ok(catalog.part(id,"manifest",null));}
    @GetMapping("/{id}/bundle") Api bundle(@PathVariable String id){return Api.ok(catalog.bundle(id));}
    @GetMapping("/{id}/metrics") Api metrics(@PathVariable String id,@RequestParam(required=false)String testSet){return Api.ok(catalog.part(id,"metrics",testSet));}
    @GetMapping("/{id}/curves") Api curves(@PathVariable String id,@RequestParam(required=false)String testSet){return Api.ok(catalog.part(id,"curves",testSet));}
    @GetMapping("/{id}/history") Api history(@PathVariable String id){return Api.ok(catalog.part(id,"history",null));}
    @GetMapping("/{id}/search") Api search(@PathVariable String id){return Api.ok(catalog.part(id,"search",null));}
}
