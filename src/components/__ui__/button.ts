import { computed, defineComponent, h } from 'vue'

type Variant = 'default' | 'destructive' | 'outline' | 'ghost'
type Size = 'default' | 'sm' | 'lg' | 'icon'

const variantClasses: Record<Variant, string> = {
  default: 'bg-primary text-primary-foreground hover:bg-primary/90',
  destructive: 'bg-red-600 text-white hover:bg-red-600/90',
  outline: 'border border-input hover:bg-accent hover:text-accent-foreground',
  ghost: 'hover:bg-muted'
}

const sizeClasses: Record<Size, string> = {
  default: 'h-10 px-4 py-2',
  sm: 'h-9 px-3',
  lg: 'h-11 px-8',
  icon: 'h-10 w-10'
}

const baseClasses = 'inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 ring-offset-background'

export const Button = defineComponent({
  name: 'UiButton',
  props: {
    as: {
      type: String,
      default: 'button'
    },
    variant: {
      type: String,
      default: 'default'
    },
    size: {
      type: String,
      default: 'default'
    }
  },
  setup(props, { slots, attrs }) {
    const classes = computed(() => {
      const variant = variantClasses[(props.variant as Variant) ?? 'default'] ?? variantClasses.default
      const size = sizeClasses[(props.size as Size) ?? 'default'] ?? sizeClasses.default
      const extra = attrs.class ? String(attrs.class) : ''
      return [baseClasses, variant, size, extra].filter(Boolean).join(' ')
    })

    return () => {
      const { class: _c, ...rest } = attrs
      return h(props.as, { ...rest, class: classes.value }, slots.default ? slots.default() : [])
    }
  }
})

export default Button
