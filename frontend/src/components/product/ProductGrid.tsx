import React from "react";
import { ProductListItemOut } from "../../types/api";
import { ProductCard } from "./ProductCard";

export interface ProductGridProps {
  products: ProductListItemOut[];
  onSelectProduct: (id: string) => void;
}

export const ProductGrid: React.FC<ProductGridProps> = ({ products, onSelectProduct }) => {
  return (
    <div className="product-grid" data-testid="product-grid">
      {products.map((product) => (
        <ProductCard key={product.id} product={product} onSelect={onSelectProduct} />
      ))}
    </div>
  );
};
