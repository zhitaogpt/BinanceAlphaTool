import { defineComponent, h } from 'vue'

export const Toaster = defineComponent({
  name: 'UiToaster',
  setup(_, { slots }) {
    return () => h('div', { class: 'toaster-container pointer-events-none fixed inset-0 z-[10000] flex items-end gap-2 p-4 sm:items-start' }, slots.default ? slots.default() : [])
  }
})

export default Toaster
