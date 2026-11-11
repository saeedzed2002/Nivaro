/** Generated from contracts/openapi/catalog.json. Run pnpm contracts:generate. */
export interface paths {
    "/api/v1/admin/catalog/categories": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Categories */
        get: operations["listAdminCategories"];
        put?: never;
        /** Create */
        post: operations["createAdminCategory"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/catalog/categories/{category_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Edit */
        put: operations["updateAdminCategory"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/catalog/categories/{category_id}/audit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Audit */
        get: operations["listAdminCategoryAudit"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/catalog/images/{job_id}/{width}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Private Output */
        get: operations["getAdminProductImage"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/catalog/products": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Products */
        get: operations["listAdminProducts"];
        put?: never;
        /** Create */
        post: operations["createAdminProduct"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/catalog/products/{product_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Detail */
        get: operations["getAdminProduct"];
        /** Edit */
        put: operations["updateAdminProduct"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/catalog/products/{product_id}/audit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Audit */
        get: operations["listAdminProductAudit"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/catalog/products/{product_id}/images": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Gallery */
        get: operations["listProductImages"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/catalog/products/{product_id}/images/{position}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Upload */
        put: operations["uploadProductImage"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/catalog/products/{product_id}/images/{position}/change": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Change */
        post: operations["changeProductGallery"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/catalog/products/{product_id}/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Status */
        put: operations["setAdminProductStatus"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/catalog/products/{product_id}/variants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Variant */
        post: operations["createAdminVariant"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/catalog/products/{product_id}/variants/{variant_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Edit Variant */
        put: operations["updateAdminVariant"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/catalog/products/{product_id}/variants/{variant_id}/offers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Offer */
        put: operations["setAdminOffer"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/catalog/products/{product_id}/variants/{variant_id}/stock": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Stock */
        put: operations["setAdminStock"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/catalog/build-evaluations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Build Evaluation */
        post: operations["evaluateBuild"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/catalog/categories": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Categories */
        get: operations["listCategories"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/catalog/comparisons": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Comparison */
        post: operations["compareProducts"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/catalog/images/{job_id}/{width}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Public Output */
        get: operations["getProductImage"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/catalog/products": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Products */
        get: operations["listProducts"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/catalog/products/{product_id}/images": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Public Gallery */
        get: operations["getProductGallery"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/catalog/products/{slug}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Product */
        get: operations["getProduct"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/catalog/variant-summaries": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Variant Summaries */
        post: operations["getVariantSummaries"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/catalog/variants/{variant_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Variant */
        get: operations["getVariant"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AdminCategory */
        AdminCategory: {
            /** Child Count */
            child_count: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Image */
            image: string;
            name: components["schemas"]["Localized"];
            /** Parent Id */
            parent_id?: string | null;
            /** Product Count */
            product_count: number;
            /** Slug */
            slug: string;
            /** Version */
            version: number;
        };
        /** AdminProduct */
        AdminProduct: {
            /** Brand */
            brand: string;
            /**
             * Category Id
             * Format: uuid
             */
            category_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Image */
            image: string;
            /** Image Kind */
            image_kind: string;
            /** Image Ready */
            image_ready: boolean;
            /** Name */
            name: string;
            /** Slug */
            slug: string;
            /**
             * Status
             * @enum {string}
             */
            status: "draft" | "published" | "archived";
            /** Variant Count */
            variant_count: number;
            /** Version */
            version: number;
        };
        /** AdminProductDetail */
        AdminProductDetail: {
            /** Brand */
            brand: string;
            /**
             * Category Id
             * Format: uuid
             */
            category_id: string;
            description: components["schemas"]["Localized"];
            /** Highlights */
            highlights: string[];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Image */
            image: string;
            /** Image Kind */
            image_kind: string;
            /** Image Ready */
            image_ready: boolean;
            /** Name */
            name: string;
            /** Slug */
            slug: string;
            /**
             * Status
             * @enum {string}
             */
            status: "draft" | "published" | "archived";
            /** Variant Count */
            variant_count: number;
            /** Variants */
            variants: components["schemas"]["AdminVariant"][];
            /** Version */
            version: number;
        };
        /** AdminProductPage */
        AdminProductPage: {
            /** Items */
            items: components["schemas"]["AdminProduct"][];
            /** Page */
            page: number;
            /** Page Size */
            page_size: number;
            /** Total */
            total: number;
        };
        /** AdminVariant */
        AdminVariant: {
            /** Evidence */
            evidence?: components["schemas"]["Evidence"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Offers */
            offers?: components["schemas"]["Offer"][];
            /**
             * On Hand
             * @default 0
             */
            on_hand: number;
            packaging: components["schemas"]["Localized"];
            /**
             * Reserved
             * @default 0
             */
            reserved: number;
            /** Sku */
            sku: string;
            /**
             * Spec Version
             * @default 1
             */
            spec_version: number;
            /** Specifications */
            specifications: components["schemas"]["CPU"] | components["schemas"]["Motherboard"] | components["schemas"]["Memory"] | components["schemas"]["Storage"] | components["schemas"]["Case"] | components["schemas"]["PSU"] | components["schemas"]["Cooler"] | components["schemas"]["GPU"] | components["schemas"]["Peripheral"] | components["schemas"]["Prebuilt"];
            /**
             * Stock Kind
             * @enum {string}
             */
            stock_kind: "component" | "accessory" | "stocked_prebuilt";
            /**
             * Stock Verified
             * @default false
             */
            stock_verified: boolean;
            /** Version */
            version: number;
        };
        /** AuditEntry */
        AuditEntry: {
            /** Action */
            action: string;
            /**
             * Actor Id
             * Format: uuid
             */
            actor_id: string;
            /** After */
            after: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /** Before */
            before: {
                [key: string]: components["schemas"]["JsonValue"];
            };
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Reason */
            reason: string;
            /** Request Id */
            request_id: string;
            /**
             * Target Id
             * Format: uuid
             */
            target_id: string;
        };
        /** AuditPage */
        AuditPage: {
            /** Items */
            items: components["schemas"]["AuditEntry"][];
            /** Page */
            page: number;
            /** Page Size */
            page_size: number;
            /** Total */
            total: number;
        };
        /** CPU */
        CPU: {
            /** Cores */
            cores?: number | null;
            /** Included Cooler */
            included_cooler?: boolean | null;
            /** Included Cooler Height Mm */
            included_cooler_height_mm?: number | null;
            /** Integrated Graphics */
            integrated_graphics?: boolean | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "cpu";
            /** Max Memory Gb */
            max_memory_gb?: number | null;
            /** Max Package Power W */
            max_package_power_w?: number | null;
            /** Memory Generation */
            memory_generation?: ("DDR4" | "DDR5") | null;
            /** Model */
            model: string;
            /** Socket */
            socket?: string | null;
            /** Tdp W */
            tdp_w?: number | null;
            /** Threads */
            threads?: number | null;
        };
        /** Case */
        Case: {
            /** Drive Bays */
            drive_bays?: {
                [key: string]: number;
            } | null;
            /** Expansion Slots */
            expansion_slots?: number | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "case";
            /** Max Cooler Height Mm */
            max_cooler_height_mm?: number | null;
            /** Max Gpu Height Mm */
            max_gpu_height_mm?: number | null;
            /** Max Gpu Length Mm */
            max_gpu_length_mm?: number | null;
            /** Max Psu Length Mm */
            max_psu_length_mm?: number | null;
            /** Motherboard Forms */
            motherboard_forms?: string[] | null;
            /** Psu Forms */
            psu_forms?: string[] | null;
        };
        /** Category */
        Category: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Image */
            image: string;
            name: components["schemas"]["Localized"];
            /** Parent Id */
            parent_id?: string | null;
            /** Slug */
            slug: string;
        };
        /** CategoryContent */
        CategoryContent: {
            name: components["schemas"]["Localized"];
            /** Parent Id */
            parent_id?: string | null;
            /** Slug */
            slug: string;
        };
        /** CategoryEdit */
        CategoryEdit: {
            /** Expected Version */
            expected_version: number;
            name: components["schemas"]["Localized"];
            /** Parent Id */
            parent_id?: string | null;
            /** Slug */
            slug: string;
        };
        /** Comparison */
        Comparison: {
            /** Category */
            category: string;
            /** Columns */
            columns: components["schemas"]["ComparisonColumn"][];
            /**
             * Currency
             * @enum {string}
             */
            currency: "IRR" | "USD";
            /**
             * Declares Winner
             * @default false
             * @constant
             */
            declares_winner: false;
            /**
             * Market
             * @enum {string}
             */
            market: "ir" | "international";
            /** Rows */
            rows: components["schemas"]["ComparisonRow"][];
        };
        /** ComparisonColumn */
        ComparisonColumn: {
            /** Name */
            name: string;
            offer: components["schemas"]["Offer"] | null;
            /**
             * Product Id
             * Format: uuid
             */
            product_id: string;
            /** Slug */
            slug: string;
            variant: components["schemas"]["Variant"];
        };
        /** ComparisonRequest */
        ComparisonRequest: {
            /**
             * Currency
             * @enum {string}
             */
            currency: "IRR" | "USD";
            /**
             * Market
             * @enum {string}
             */
            market: "ir" | "international";
            /** Variant Ids */
            variant_ids: string[];
        };
        /** ComparisonRow */
        ComparisonRow: {
            /** Different */
            different: boolean;
            /** Key */
            key: string;
            /** Values */
            values: (string | number | boolean | null)[];
        };
        /** Cooler */
        Cooler: {
            /** Approved Cpu Models */
            approved_cpu_models?: string[] | null;
            /** Cooling Type */
            cooling_type?: ("air" | "liquid") | null;
            /** Height Mm */
            height_mm?: number | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "cooler";
            /** Max Memory Height Mm */
            max_memory_height_mm?: number | null;
            /** Sockets */
            sockets?: string[] | null;
        };
        /** ErrorDetail */
        ErrorDetail: {
            /** Code */
            code: string;
            /** Details */
            details?: string[];
            /** Message */
            message: string;
            /** Request Id */
            request_id: string;
        };
        /** ErrorEnvelope */
        ErrorEnvelope: {
            error: components["schemas"]["ErrorDetail"];
        };
        /** Evaluation */
        Evaluation: {
            /** Assembly Fee Minor */
            assembly_fee_minor?: null;
            /** Component Subtotal Minor */
            component_subtotal_minor: number;
            /**
             * Currency
             * @enum {string}
             */
            currency: "IRR" | "USD";
            /** Estimated Power W */
            estimated_power_w: number | null;
            /**
             * Evaluated At
             * Format: date-time
             */
            evaluated_at: string;
            /** Findings */
            findings: components["schemas"]["Finding"][];
            /**
             * Market
             * @enum {string}
             */
            market: "ir" | "international";
            /**
             * Mode
             * @enum {string}
             */
            mode: "complete_build" | "parts_only";
            /** Peripheral Subtotal Minor */
            peripheral_subtotal_minor: number;
            /** Power Method */
            power_method: string;
            /**
             * Price Basis
             * @default reference_only_not_payable
             * @constant
             */
            price_basis: "reference_only_not_payable";
            /**
             * Reserves Stock
             * @default false
             * @constant
             */
            reserves_stock: false;
            /** Ruleset Version */
            ruleset_version: string;
            /** Selection Hash */
            selection_hash: string;
            /** Shipping Minor */
            shipping_minor?: null;
            /** Spec Versions */
            spec_versions: {
                [key: string]: number;
            };
            /** Stale Reasons */
            stale_reasons: ("selection_changed" | "specifications_changed" | "rules_changed")[];
            /**
             * Status
             * @enum {string}
             */
            status: "compatible" | "incompatible" | "needs_review" | "incomplete";
            /** Tax Minor */
            tax_minor?: null;
            /** Unavailable Slots */
            unavailable_slots: string[];
            /** Unpriced Slots */
            unpriced_slots: string[];
        };
        /** EvaluationRequest */
        EvaluationRequest: {
            /**
             * Currency
             * @enum {string}
             */
            currency: "IRR" | "USD";
            /**
             * Market
             * @enum {string}
             */
            market: "ir" | "international";
            /**
             * Mode
             * @default complete_build
             * @enum {string}
             */
            mode: "complete_build" | "parts_only";
            previous?: components["schemas"]["Revision"] | null;
            /**
             * Requires Dedicated Gpu
             * @default false
             */
            requires_dedicated_gpu: boolean;
            /** Selections */
            selections?: components["schemas"]["Selection"][];
        };
        /** Evidence */
        Evidence: {
            /**
             * Checked On
             * Format: date
             */
            checked_on: string;
            /** Note */
            note: string;
            /**
             * Url
             * Format: uri
             */
            url: string;
        };
        /** Finding */
        Finding: {
            /** Code */
            code: string;
            corrective_action: components["schemas"]["Localized"];
            /** Evidence */
            evidence: components["schemas"]["Evidence"][];
            message: components["schemas"]["Localized"];
            /** Ruleset Version */
            ruleset_version: string;
            /** Slots */
            slots: string[];
            /**
             * Status
             * @enum {string}
             */
            status: "compatible" | "incompatible" | "needs_review" | "incomplete";
        };
        /** GPU */
        GPU: {
            /** Board Power W */
            board_power_w?: number | null;
            /** Height Mm */
            height_mm?: number | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "gpu";
            /** Length Mm */
            length_mm?: number | null;
            /** Power Connectors */
            power_connectors?: {
                [key: string]: number;
            } | null;
            /** Recommended Psu W */
            recommended_psu_w?: number | null;
            /** Slots */
            slots?: number | null;
            /** Vram Gb */
            vram_gb?: number | null;
        };
        /** GalleryChange */
        GalleryChange: {
            /** Destination */
            destination?: number | null;
            /** Expected Version */
            expected_version: number;
        };
        JsonValue: unknown;
        /** Localized */
        Localized: {
            /** En */
            en: string;
            /** Fa */
            fa: string;
        };
        /** MediaGallery */
        MediaGallery: {
            /** Items */
            items: components["schemas"]["MediaSlot"][];
            /** Version */
            version: number;
        };
        /** MediaJob */
        MediaJob: {
            /** Error Code */
            error_code: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * State
             * @enum {string}
             */
            state: "uploaded" | "processing" | "ready" | "failed";
        };
        /** MediaSlot */
        MediaSlot: {
            active: components["schemas"]["MediaJob"] | null;
            /** Alt */
            alt: {
                [key: string]: string;
            };
            /**
             * Image Kind
             * @default illustration
             * @enum {string}
             */
            image_kind: "illustration" | "exact_sku";
            pending: components["schemas"]["MediaJob"] | null;
            /** Position */
            position: number;
            /** Urls */
            urls: {
                [key: string]: string;
            };
        };
        /** Memory */
        Memory: {
            /** Capacity Gb */
            capacity_gb?: number | null;
            /** Generation */
            generation?: ("DDR4" | "DDR5") | null;
            /** Height Mm */
            height_mm?: number | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "memory";
            /** Modules */
            modules?: number | null;
        };
        /** Motherboard */
        Motherboard: {
            /** Bios Revision */
            bios_revision?: string | null;
            /** Form Factor */
            form_factor?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "motherboard";
            /** Max Memory Gb */
            max_memory_gb?: number | null;
            /** Memory Generation */
            memory_generation?: ("DDR4" | "DDR5") | null;
            /** Memory Slots */
            memory_slots?: number | null;
            /** Power Connectors */
            power_connectors?: {
                [key: string]: number;
            } | null;
            /** Socket */
            socket?: string | null;
            /** Storage Form Factors */
            storage_form_factors?: string[] | null;
            /** Storage Interfaces */
            storage_interfaces?: {
                [key: string]: number;
            } | null;
            /** Verified Bios Revision */
            verified_bios_revision?: string | null;
            /** Verified Cpu Models */
            verified_cpu_models?: string[] | null;
        };
        /** Offer */
        Offer: {
            /** Amount Minor */
            amount_minor: number;
            /**
             * Available For Sale
             * @default false
             */
            available_for_sale: boolean;
            /**
             * Currency
             * @enum {string}
             */
            currency: "IRR" | "USD";
            /**
             * Market
             * @enum {string}
             */
            market: "ir" | "international";
            /**
             * Price Version
             * @default 1
             */
            price_version: number;
            /**
             * Reference Only
             * @default true
             */
            reference_only: boolean;
            /** Seller */
            seller: string;
            source: components["schemas"]["Evidence"];
        };
        /** OfferChange */
        OfferChange: {
            /** Amount Minor */
            amount_minor: number;
            /** Available For Sale */
            available_for_sale: boolean;
            /**
             * Currency
             * @enum {string}
             */
            currency: "IRR" | "USD";
            /** Expected Price Version */
            expected_price_version: number;
            /** Expected Version */
            expected_version: number;
            /**
             * Market
             * @enum {string}
             */
            market: "ir" | "international";
            /** Reason */
            reason: string;
            /** Reference Only */
            reference_only: boolean;
            /** Seller */
            seller: string;
            source: components["schemas"]["Evidence"];
        };
        /** PSU */
        PSU: {
            /** Connectors */
            connectors?: {
                [key: string]: number;
            } | null;
            /** Form Factor */
            form_factor?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "psu";
            /** Length Mm */
            length_mm?: number | null;
            /** Wattage W */
            wattage_w?: number | null;
        };
        /** Peripheral */
        Peripheral: {
            /** Connection */
            connection?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "peripheral";
            /**
             * Role
             * @enum {string}
             */
            role: "monitor" | "keyboard" | "mouse" | "audio" | "chair" | "desk" | "accessory";
        };
        /** Prebuilt */
        Prebuilt: {
            /** Component Descriptions */
            component_descriptions?: string[];
            /** Cpu Model */
            cpu_model?: string | null;
            /** Gpu Model */
            gpu_model?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "prebuilt";
            /** Memory Gb */
            memory_gb?: number | null;
            /** Storage Gb */
            storage_gb?: number | null;
        };
        /** Product */
        Product: {
            /** Brand */
            brand: string;
            /** Category */
            category: string;
            description: components["schemas"]["Localized"];
            /** Highlights */
            highlights?: string[];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Image */
            image: string;
            /**
             * Image Kind
             * @default illustration
             * @enum {string}
             */
            image_kind: "illustration" | "exact_sku";
            /** Name */
            name: string;
            /** Slug */
            slug: string;
            /** Variants */
            variants: components["schemas"]["Variant"][];
        };
        /** ProductContent */
        ProductContent: {
            /**
             * Brand
             * @default
             */
            brand: string;
            /**
             * Category Id
             * Format: uuid
             */
            category_id: string;
            description: components["schemas"]["Localized"];
            /** Highlights */
            highlights?: string[];
            /** Name */
            name: string;
            /** Slug */
            slug: string;
        };
        /** ProductEdit */
        ProductEdit: {
            /**
             * Brand
             * @default
             */
            brand: string;
            /**
             * Category Id
             * Format: uuid
             */
            category_id: string;
            description: components["schemas"]["Localized"];
            /** Expected Version */
            expected_version: number;
            /** Highlights */
            highlights?: string[];
            /** Name */
            name: string;
            /** Slug */
            slug: string;
        };
        /** ProductPage */
        ProductPage: {
            /** Items */
            items: components["schemas"]["Product"][];
            /** Page */
            page: number;
            /** Page Size */
            page_size: number;
            /** Total */
            total: number;
        };
        /** PublicImage */
        PublicImage: {
            /** Alt */
            alt: {
                [key: string]: string;
            };
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Image Kind
             * @enum {string}
             */
            image_kind: "illustration" | "exact_sku";
            /** Urls */
            urls: {
                [key: string]: string;
            };
        };
        /** Revision */
        Revision: {
            /** Ruleset Version */
            ruleset_version: string;
            /** Selection Hash */
            selection_hash: string;
            /** Spec Versions */
            spec_versions: {
                [key: string]: number;
            };
        };
        /** Selection */
        Selection: {
            /**
             * Quantity
             * @default 1
             */
            quantity: number;
            /**
             * Role
             * @enum {string}
             */
            role: "cpu" | "motherboard" | "memory" | "storage" | "case" | "psu" | "cooler" | "gpu" | "monitor" | "keyboard" | "mouse" | "audio" | "chair" | "desk" | "accessory";
            /** Slot Key */
            slot_key: string;
            /**
             * Variant Id
             * Format: uuid
             */
            variant_id: string;
        };
        /** StatusChange */
        StatusChange: {
            /** Expected Version */
            expected_version: number;
            /**
             * Status
             * @enum {string}
             */
            status: "draft" | "published" | "archived";
        };
        /** StockChange */
        StockChange: {
            /** Expected Stock Version */
            expected_stock_version: number;
            /** Expected Version */
            expected_version: number;
            /** On Hand */
            on_hand: number;
            /** Reason */
            reason: string;
            /** Stock Verified */
            stock_verified: boolean;
        };
        /** Storage */
        Storage: {
            /** Capacity Gb */
            capacity_gb?: number | null;
            /** Form Factor */
            form_factor?: string | null;
            /** Interface */
            interface?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "storage";
        };
        /** SummaryRequest */
        SummaryRequest: {
            /**
             * Currency
             * @enum {string}
             */
            currency: "IRR" | "USD";
            /**
             * Market
             * @enum {string}
             */
            market: "ir" | "international";
            /** Variant Ids */
            variant_ids: string[];
        };
        /** SummaryResponse */
        SummaryResponse: {
            /**
             * Currency
             * @enum {string}
             */
            currency: "IRR" | "USD";
            /** Items */
            items: components["schemas"]["VariantSummary"][];
            /**
             * Market
             * @enum {string}
             */
            market: "ir" | "international";
            /** Missing Ids */
            missing_ids: string[];
            /**
             * Reserves Stock
             * @default false
             * @constant
             */
            reserves_stock: false;
        };
        /** Variant */
        Variant: {
            /** Evidence */
            evidence?: components["schemas"]["Evidence"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Offers */
            offers?: components["schemas"]["Offer"][];
            /**
             * On Hand
             * @default 0
             */
            on_hand: number;
            packaging: components["schemas"]["Localized"];
            /**
             * Reserved
             * @default 0
             */
            reserved: number;
            /** Sku */
            sku: string;
            /**
             * Spec Version
             * @default 1
             */
            spec_version: number;
            /** Specifications */
            specifications: components["schemas"]["CPU"] | components["schemas"]["Motherboard"] | components["schemas"]["Memory"] | components["schemas"]["Storage"] | components["schemas"]["Case"] | components["schemas"]["PSU"] | components["schemas"]["Cooler"] | components["schemas"]["GPU"] | components["schemas"]["Peripheral"] | components["schemas"]["Prebuilt"];
            /**
             * Stock Kind
             * @enum {string}
             */
            stock_kind: "component" | "accessory" | "stocked_prebuilt";
            /**
             * Stock Verified
             * @default false
             */
            stock_verified: boolean;
        };
        /** VariantContent */
        VariantContent: {
            /** Evidence */
            evidence?: components["schemas"]["Evidence"][];
            /** Expected Version */
            expected_version: number;
            packaging: components["schemas"]["Localized"];
            /** Sku */
            sku: string;
            /** Specifications */
            specifications: components["schemas"]["CPU"] | components["schemas"]["Motherboard"] | components["schemas"]["Memory"] | components["schemas"]["Storage"] | components["schemas"]["Case"] | components["schemas"]["PSU"] | components["schemas"]["Cooler"] | components["schemas"]["GPU"] | components["schemas"]["Peripheral"] | components["schemas"]["Prebuilt"];
        };
        /** VariantSummary */
        VariantSummary: {
            /** Available Quantity */
            available_quantity: number | null;
            /** Image */
            image: string;
            /**
             * Image Kind
             * @enum {string}
             */
            image_kind: "illustration" | "exact_sku";
            /** Name */
            name: string;
            offer: components["schemas"]["Offer"] | null;
            /**
             * Product Id
             * Format: uuid
             */
            product_id: string;
            /** Sku */
            sku: string;
            /** Slug */
            slug: string;
            /**
             * Variant Id
             * Format: uuid
             */
            variant_id: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    listAdminCategories: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminCategory"][];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    createAdminCategory: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CategoryContent"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminCategory"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    updateAdminCategory: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                category_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CategoryEdit"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminCategory"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    listAdminCategoryAudit: {
        parameters: {
            query?: {
                page?: number;
                page_size?: number;
            };
            header?: never;
            path: {
                category_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditPage"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    getAdminProductImage: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
                width: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    listAdminProducts: {
        parameters: {
            query?: {
                q?: string;
                status?: ("draft" | "published" | "archived") | null;
                category_id?: string | null;
                page?: number;
                page_size?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminProductPage"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    createAdminProduct: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProductContent"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminProductDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    getAdminProduct: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                product_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminProductDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    updateAdminProduct: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                product_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProductEdit"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminProductDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    listAdminProductAudit: {
        parameters: {
            query?: {
                page?: number;
                page_size?: number;
            };
            header?: never;
            path: {
                product_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditPage"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    listProductImages: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                product_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MediaGallery"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    uploadProductImage: {
        parameters: {
            query: {
                expected_version: number;
                alt_fa: string;
                alt_en: string;
                image_kind?: "illustration" | "exact_sku";
            };
            header?: never;
            path: {
                product_id: string;
                position: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/octet-stream": string;
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MediaJob"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    changeProductGallery: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                product_id: string;
                position: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GalleryChange"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: boolean;
                    };
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    setAdminProductStatus: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                product_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StatusChange"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminProductDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    createAdminVariant: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                product_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VariantContent"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminProductDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    updateAdminVariant: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                product_id: string;
                variant_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VariantContent"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminProductDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    setAdminOffer: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                product_id: string;
                variant_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OfferChange"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminProductDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    setAdminStock: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                product_id: string;
                variant_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StockChange"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminProductDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    evaluateBuild: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EvaluationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Evaluation"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    listCategories: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Category"][];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    compareProducts: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ComparisonRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Comparison"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    getProductImage: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
                width: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    listProducts: {
        parameters: {
            query?: {
                q?: string;
                category?: string;
                brand?: string;
                market?: "ir" | "international";
                sort?: "featured" | "name" | "newest" | "price_asc" | "price_desc";
                page?: number;
                page_size?: number;
                min_price?: number | null;
                max_price?: number | null;
                in_stock?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProductPage"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    getProductGallery: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                product_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublicImage"][];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Content Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    getProduct: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                slug: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Product"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    getVariantSummaries: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SummaryRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SummaryResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    getVariant: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                variant_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Variant"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
}
