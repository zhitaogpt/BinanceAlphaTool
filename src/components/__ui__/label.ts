import { defineComponent, h } from 'vue'

const baseClasses = 'text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70'

export const Label = defineComponent({
  name: 'UiLabel',
  setup(_, { slots, attrs }) {
    return () => {
      const { class: extraClass, ...rest } = attrs
      const classes = [baseClasses, extraClass ? String(extraClass) : ''].filter(Boolean).join(' ')
      return h('label', { ...rest, class: classes }, slots.default ? slots.default() : [])
    }
  }
})

export default Label
