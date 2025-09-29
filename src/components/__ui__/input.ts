import { defineComponent, h } from 'vue'

type ModelValue = string | number | null | undefined

const baseClasses = 'flex h-10 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50'

export const Input = defineComponent({
  name: 'UiInput',
  props: {
    modelValue: {
      type: [String, Number],
      default: ''
    }
  },
  emits: ['update:modelValue'],
  setup(props, { emit, attrs }) {
    const onInput = (event: Event) => {
      const target = event.target as HTMLInputElement
      emit('update:modelValue', target.value)
    }

    return () => {
      const { class: extraClass, ...rest } = attrs
      const classes = [baseClasses, extraClass ? String(extraClass) : ''].filter(Boolean).join(' ')

      return h('input', {
        ...rest,
        class: classes,
        value: (props.modelValue as ModelValue) ?? '',
        onInput
      })
    }
  }
})

export default Input
