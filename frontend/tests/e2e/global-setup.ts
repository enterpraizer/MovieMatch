import { execSync } from "child_process";

export default function globalSetup() {
  try {
    execSync(
      'docker exec moviematch-redis-1 redis-cli -n 0 EVAL "for _,k in ipairs(redis.call(\'keys\',\'rl:*\')) do redis.call(\'del\',k) end" 0',
      { stdio: "pipe" }
    );
  } catch {
    // Redis flush is best-effort
  }
}
