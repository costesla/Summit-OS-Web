/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                tesla: {
                    red: '#E82127',
                    gray: '#393939',
                    dark: '#171a20',
                }
            }
        },
    },
    plugins: [],
}
