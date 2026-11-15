import type { ComponentPropsWithoutRef } from 'react';

type ButtonProps = ComponentPropsWithoutRef<'button'> & {
  variant?: 'primary' | 'ghost' | 'outline';
};

export default function Button({ variant, className, type = 'button', ...props }: ButtonProps) {
  const classes = [variant ? `btn ${variant}` : undefined, className].filter(Boolean).join(' ');
  return <button type={type} className={classes || undefined} {...props} />;
}
