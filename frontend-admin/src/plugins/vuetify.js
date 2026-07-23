import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'

// Tema Vuetify memakai warna brand ASP supaya konsisten dengan sisa portal
export default createVuetify({
  icons: { defaultSet: 'mdi' },
  theme: {
    defaultTheme: 'asp',
    themes: {
      asp: {
        dark: false,
        colors: {
          primary: '#1466b3',
          secondary: '#0b3a63',
          error: '#dc2626',
          surface: '#ffffff',
          background: '#f8fafc',
        },
      },
    },
  },
})
