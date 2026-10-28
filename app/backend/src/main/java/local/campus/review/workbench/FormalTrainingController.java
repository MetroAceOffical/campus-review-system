package local.campus.review.workbench;

import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/workbench/training")
public class FormalTrainingController {
    private final FormalTrainingService progress;private final CurrentUserService users;
    public FormalTrainingController(FormalTrainingService progress,CurrentUserService users){this.progress=progress;this.users=users;}
    @GetMapping("/formal-progress") Api get(Authentication auth){return Api.ok(progress.progress(users.require(auth)));}
}
