<script setup lang="ts">
import { useRouter } from 'vue-router'
import LoginForm from '../components/LoginForm.vue'
import { home, session } from '../session'
const router = useRouter()
function authenticated() { if (session.user) router.replace(home(session.user.role)) }
</script>
<template>
  <main class="login-page campus-login"><section class="login-story"><div class="login-school"><img :src="'/brand/cucn-emblem.png'" alt="南京传媒学院校徽" /><img class="school-wordmark" :src="'/brand/cucn-wordmark.png'" alt="南京传媒学院" /></div><span class="eyebrow">CAMPUS CONTENT WORKSPACE</span><h1>让每一份校园稿件<br />清晰、有据、有序。</h1><p>从创作与内容检查，到审核发布，<br />在同一个工作台完成图文稿件的流转。</p><div class="login-capabilities"><span>文本复用</span><span>语法检查</span><span>图文核对</span><span>模型训练</span></div><div class="login-art" aria-hidden="true"><div class="art-sheet"><span /><span /><span /><i /><span /><span /></div><div class="art-check">✓</div><div class="art-grid" /></div><small>南京传媒学院 · 校园图文审核系统</small></section><section class="login-panel"><div class="eyebrow">进入工作空间</div><h2>欢迎登录</h2><p class="muted">使用你的校内工作账号继续</p><LoginForm @authenticated="authenticated" /><div class="login-role-note">创作者编写稿件 · 审核员处理审核 · 管理员维护数据与模型</div></section></main>
</template>
