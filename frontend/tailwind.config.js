/** @type {import('tailwindcss').Config} */

// Colours are CSS variables (src/index.css) holding "R G B", so one class
// serves both themes and opacity modifiers still work (bg-accent/10).
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`

export default {
  darkMode: 'selector',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Semantic tokens: use these in pages and components
        paper: v('paper'), // page background
        surface: v('surface'), // controls, sticky bars, popovers
        subtle: v('subtle'), // table header, row hover
        tint: v('tint'), // neutral fills (chips, selected rows)
        ink: {
          DEFAULT: v('ink'), // headings, figures, primary text
          2: v('ink-2'), // body text, secondary text
          3: v('ink-3'), // labels, metadata (still 4.5:1)
        },
        rule: {
          DEFAULT: v('rule'), // hairline separators (decorative)
          strong: v('rule-strong'), // control borders (3:1)
        },
        accent: {
          DEFAULT: v('accent'), // links, focus, the selected item in a chart
          strong: v('accent-strong'), // link hover
          tint: v('accent-tint'), // highlighted option background
        },
        attention: v('attention'), // flags that question a figure (with an icon, never alone)
        danger: v('danger'), // load errors
        // Tailwind's gray and the old primary scale, mapped onto the same
        // neutrals and accent, for code that still names them
        gray: {
          50: '#F6F7F8',
          100: '#EDEFF1',
          200: '#E1E4E8',
          300: '#C9CED4',
          400: '#9AA1AB',
          500: '#6B727C',
          600: '#4F5660',
          700: '#3D434B',
          800: '#272C33',
          900: '#181B1F',
          950: '#111315',
        },
        primary: {
          50: '#EEF3F9',
          100: '#DCE7F3',
          200: '#B9CFE6',
          300: '#93B9E0',
          400: '#8CB8E6',
          500: '#3A73AE',
          600: '#1D5A96',
          700: '#154675',
          800: '#10375C',
          900: '#0D2B48',
          950: '#081C30',
        },
      },
      fontFamily: {
        sans: ['"CSD Sans"', '"CSD Sans Fallback"', 'system-ui', '-apple-system', '"Segoe UI"', 'Roboto', 'Arial', 'sans-serif'],
        serif: ['"CSD Serif"', '"CSD Serif Fallback"', 'Georgia', 'Cambria', '"Times New Roman"', 'serif'],
      },
      // The type scale. Pages use these names; Tailwind's own sizes remain
      // for the few places that still use them.
      fontSize: {
        display: ['2rem', { lineHeight: '1.15', letterSpacing: '-0.01em' }], // page title (h1)
        title: ['1.4375rem', { lineHeight: '1.25', letterSpacing: '-0.005em' }], // section (h2)
        heading: ['1.0625rem', { lineHeight: '1.4' }], // subsection (h3)
        body: ['1rem', { lineHeight: '1.65' }], // prose
        ui: ['0.9375rem', { lineHeight: '1.45' }], // controls, table cells
        meta: ['0.8125rem', { lineHeight: '1.5' }], // notes, labels, metadata
        label: ['0.75rem', { lineHeight: '1.35', letterSpacing: '0.01em' }], // small labels
        figure: ['1.75rem', { lineHeight: '1.1', letterSpacing: '-0.01em' }], // a key number
      },
      maxWidth: {
        prose: '42rem', // reading measure, about 70 characters
        page: '76rem',
      },
      boxShadow: {
        // Floating layers only (popovers, menus); everything else uses rules
        pop: '0 4px 16px -4px rgb(0 0 0 / 0.14), 0 1px 3px rgb(0 0 0 / 0.08)',
      },
      spacing: {
        header: 'var(--header-h)',
      },
    },
  },
  plugins: [],
}
