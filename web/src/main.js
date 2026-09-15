import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import Books from './views/Books.vue'
import NewTask from './views/NewTask.vue'
import Progress from './views/Progress.vue'
import Output from './views/Output.vue'
import Toolbox from './views/Toolbox.vue'
import Settings from './views/Settings.vue'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'books', component: Books },
    { path: '/new', name: 'new', component: NewTask },
    { path: '/progress', name: 'progress', component: Progress },
    { path: '/output', name: 'output', component: Output },
    { path: '/toolbox', name: 'toolbox', component: Toolbox },
    { path: '/settings', name: 'settings', component: Settings },
  ],
})

createApp(App).use(router).mount('#app')
