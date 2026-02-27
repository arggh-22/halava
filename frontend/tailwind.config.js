/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    darkMode: "class",
    theme: {
        extend: {
            colors: {
                "primary": "#0586c7",
                "background-light": "#f5f7f8",
                "background-dark": "#0f1c23",
                "ios-dark": "#0a0a0a",
                "ios-card": "#1c1c1e",
                "ios-card-hover": "#2c2c2e",
                "success": "#34c759",
                "verified": "#00c4b4", // Tealish green for verified
            },
            fontFamily: {
                "display": ["Inter", "sans-serif"]
            },
            borderRadius: {
                "lg": "2rem",
                "xl": "3rem",
            },
        },
    },
    plugins: [],
}
