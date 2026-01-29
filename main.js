document.addEventListener("DOMContentLoaded", () => {
  const donateBtn = document.getElementById("donateBtn");
  if (donateBtn) {
    donateBtn.addEventListener("click", () => {
      alert("寄附の詳細は現在準備中です。\n銀行振込などの情報は後日掲載予定です。");
    });
  }

  const subsidyList = document.getElementById("subsidyList");
  const subsidies = [
    "自治体の福祉関連補助金",
    "民間財団の助成金",
    "地域活動支援助成金"
  ];

  subsidies.forEach(item => {
    const li = document.createElement("li");
    li.textContent = item;
    subsidyList.appendChild(li);
  });
});
