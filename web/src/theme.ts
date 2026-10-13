import type { ThemeConfig } from "antd";

export const studioTheme: ThemeConfig = {
  token: {
    colorPrimary: "#176b5b",
    colorInfo: "#176b5b",
    colorSuccess: "#28836c",
    colorWarning: "#bd7b24",
    colorError: "#c5483d",
    colorText: "#202a27",
    colorTextSecondary: "#697571",
    colorBgLayout: "#f3f5f4",
    colorBgContainer: "#ffffff",
    colorBorderSecondary: "#e6eae8",
    borderRadius: 8,
    controlHeight: 38,
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif",
  },
  components: {
    Layout: { bodyBg: "#f3f5f4", siderBg: "#ffffff", headerBg: "#ffffff" },
    Card: { headerBg: "transparent" },
    Button: { fontWeight: 550 },
  },
};
