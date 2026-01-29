const buttons = document.querySelectorAll(".amount-btn");
const output = document.getElementById("selectedAmount");

buttons.forEach(btn => {
  btn.addEventListener("click", () => {
    const amount = btn.dataset.amount;
    output.textContent = `選択された寄付額：${amount}円`;
  });
});

// スクロールで寄付ボタン強調
window.addEventListener("scroll", () => {
  const cta = document.querySelector(".cta-float");
  if (window.scrollY > 400) {
    cta.style.transform = "scale(1.05)";
  } else {
    cta.style.transform = "scale(1)";
  }
});
