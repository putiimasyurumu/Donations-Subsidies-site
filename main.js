const light = document.querySelector(".light-rays");

let t = 0;

function animateLight() {
  if (!light) return;

  t += 0.002;

  const x = Math.sin(t) * 20;
  const scale = 1 + Math.sin(t * 0.7) * 0.05;

  light.style.transform = `translateX(${x}px) scale(${scale})`;

  requestAnimationFrame(animateLight);
}

animateLight();

const donateScrollBtn = document.getElementById("donate-scroll-btn");
const donationSection = document.getElementById("donation");

if (donateScrollBtn && donationSection) {
  donateScrollBtn.addEventListener("click", (event) => {
    event.preventDefault();

    if (window.jQuery) {
      window.jQuery("html, body").stop().animate(
        { scrollTop: window.jQuery(donationSection).offset().top },
        600
      );
      return;
    }

    donationSection.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
  anchor.addEventListener("click", (event) => {
    if (anchor.id === "donate-scroll-btn") return;

    const hash = anchor.getAttribute("href");
    if (!hash || hash === "#") return;

    const target = document.querySelector(hash);
    if (!target) return;

    event.preventDefault();
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
});
