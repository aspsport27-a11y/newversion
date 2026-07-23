<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const showPw = ref(false)
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(username.value.trim(), password.value)
    router.push({ name: 'dashboard' })
  } catch (e) {
    error.value = e?.response?.data?.message || 'Login gagal. Periksa username/password.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <v-app>
    <div class="asp-login-bg d-flex align-center justify-center pa-4">
      <v-card class="asp-login-card mx-auto" width="100%" max-width="420" rounded="xl" elevation="10">
        <div class="asp-card-head text-center pt-8 pb-6 px-6">
          <div class="asp-logo-badge mx-auto mb-4">
            <img src="/asp-logo.png" alt="ASP Sports" height="30" style="filter: brightness(0) invert(1)" />
          </div>
          <h1 class="text-h6 font-weight-medium text-white mb-1">Selamat datang</h1>
          <p class="text-body-2 text-white" style="opacity: 0.75">Masuk ke ASP Sports Venue Management</p>
        </div>

        <v-card-text class="pa-6">
          <v-form @submit.prevent="submit">
            <v-text-field
              v-model="username"
              label="Username atau Email"
              placeholder="admin"
              prepend-inner-icon="mdi-account-outline"
              variant="outlined"
              color="primary"
              autocomplete="username"
              density="comfortable"
              class="mb-2"
              required
            />
            <v-text-field
              v-model="password"
              label="Password"
              :type="showPw ? 'text' : 'password'"
              prepend-inner-icon="mdi-lock-outline"
              :append-inner-icon="showPw ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
              @click:append-inner="showPw = !showPw"
              variant="outlined"
              color="primary"
              autocomplete="current-password"
              density="comfortable"
              required
            />

            <v-alert
              v-if="error"
              type="error"
              variant="tonal"
              density="compact"
              class="mb-4 text-body-2"
            >{{ error }}</v-alert>

            <v-btn
              type="submit"
              color="primary"
              size="large"
              block
              rounded="lg"
              :loading="loading"
              append-icon="mdi-arrow-right"
            >Masuk</v-btn>
          </v-form>
        </v-card-text>

        <v-card-text class="text-center text-caption text-medium-emphasis pt-0 pb-6">
          © {{ new Date().getFullYear() }} ASP Sports · portal.aspsports.id
        </v-card-text>
      </v-card>
    </div>
  </v-app>
</template>

<style scoped>
.asp-login-bg {
  min-height: 100vh;
  background: linear-gradient(135deg, #115592, #0d4372 55%, #0b3a63);
}
.asp-login-card {
  overflow: hidden;
}
.asp-card-head {
  background: linear-gradient(135deg, #1466b3, #0b3a63);
}
.asp-logo-badge {
  height: 60px;
  width: 60px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.25);
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
