package local.campus.review.workbench;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/workbench/training")
public class TrainingAnalyticsController {
 final TrainingAnalyticsService analytics;final CurrentUserService users;
 public TrainingAnalyticsController(TrainingAnalyticsService analytics,CurrentUserService users){this.analytics=analytics;this.users=users;}
 @GetMapping("/runs/{id}/analytics") Api get(Authentication a,@PathVariable String id)throws Exception{return Api.ok(analytics.get(users.require(a),id));}
}
