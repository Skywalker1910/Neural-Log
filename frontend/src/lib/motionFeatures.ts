/**
 * Split point for motion's feature bundle.
 *
 * LazyMotion accepts a loader function as well as a feature object; returning
 * the import here keeps ~20kB of animation machinery out of the entry chunk and
 * fetches it right after first paint. Animations are inert for those few
 * hundred milliseconds, which is exactly the right trade - content renders
 * immediately, decoration arrives a moment later.
 */
export const loadDomAnimation = () =>
  import('motion/react').then((module) => module.domAnimation)
