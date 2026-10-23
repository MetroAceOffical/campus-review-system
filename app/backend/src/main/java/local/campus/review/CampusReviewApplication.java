package local.campus.review;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@org.springframework.scheduling.annotation.EnableScheduling
public class CampusReviewApplication {
    public static void main(String[] args) { SpringApplication.run(CampusReviewApplication.class,args); }
}
