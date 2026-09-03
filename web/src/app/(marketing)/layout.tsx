import { Footer } from "@/components/ui/nav";
import { ProductTopBar, TopBarLink } from "@/components/ui/floating-nav";

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <ProductTopBar>
        <TopBarLink href="/library">Library</TopBarLink>
        <TopBarLink href="/chat">Ask</TopBarLink>
        <TopBarLink href="/review">Review</TopBarLink>
      </ProductTopBar>
      <main>{children}</main>
      <Footer />
    </>
  );
}
