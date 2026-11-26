import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '../../lib/utils'

const buttonStyles = cva('inline-flex items-center justify-center gap-2 whitespace-nowrap transition-colors disabled:pointer-events-none disabled:opacity-50', {
  variants: {
    variant: {
      primary: 'rounded bg-[#176c54] text-white hover:bg-[#105741]',
      outline: 'rounded border border-[#dfe5dc] bg-white text-[#496452] hover:border-[#91b39b]',
      ghost: 'rounded text-[#496452] hover:bg-[#edf3e6]',
    },
    size: { default: 'h-9 px-3 text-xs font-semibold', icon: 'h-9 w-9' },
  },
  defaultVariants: { variant: 'primary', size: 'default' },
})

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonStyles> {}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, ...props }, ref) => (
  <button ref={ref} className={cn(buttonStyles({ variant, size }), className)} {...props} />
))
Button.displayName = 'Button'

export { Button, buttonStyles }
