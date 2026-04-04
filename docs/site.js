const floatingNodes = document.querySelectorAll("[data-float]");

function initReveal() {
  const revealNodes = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window)) {
    revealNodes.forEach((node) => node.classList.add("is-visible"));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    {
      rootMargin: "0px 0px -10% 0px",
      threshold: 0.14,
    }
  );

  revealNodes.forEach((node) => observer.observe(node));
}

function initParallax() {
  if (!floatingNodes.length || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return;
  }

  let ticking = false;

  const update = () => {
    const shift = Math.max(-20, Math.min(14, window.scrollY * -0.035));
    document.documentElement.style.setProperty("--hero-shift", `${shift}px`);

    floatingNodes.forEach((node, index) => {
      const rect = node.getBoundingClientRect();
      const distance = (window.innerHeight * 0.5 - rect.top) * 0.012;
      const bounded = Math.max(-10, Math.min(10, distance));
      node.style.transform = `translateY(${bounded + index * 0.35}px)`;
    });

    ticking = false;
  };

  const requestTick = () => {
    if (!ticking) {
      window.requestAnimationFrame(update);
      ticking = true;
    }
  };

  update();
  window.addEventListener("scroll", requestTick, { passive: true });
  window.addEventListener("resize", requestTick);
}

window.addEventListener("DOMContentLoaded", () => {
  initReveal();
  initParallax();
});
