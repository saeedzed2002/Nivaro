/** Generated from contracts/openapi/orders.json. Run pnpm contracts:generate. */
export interface paths {
    "/api/v1/orders/checkout/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Preview */
        post: operations["previewCheckout"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/orders/checkout/{operation_id}/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Confirm */
        post: operations["confirmCheckout"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/orders/{order_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Order Status */
        get: operations["readOrderStatus"];
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
        /** CheckoutIntent */
        CheckoutIntent: {
            /**
             * Address Id
             * Format: uuid
             */
            address_id: string;
            /** Address Version */
            address_version: number;
            /** Cart Version */
            cart_version: number;
            /** Coupon Code */
            coupon_code?: string | null;
            currency: components["schemas"]["Currency"];
            market: components["schemas"]["Market"];
        };
        /** ConfirmPreview */
        ConfirmPreview: {
            /** Confirmation */
            confirmation: string;
        };
        /** @enum {string} */
        Currency: "IRR" | "USD";
        /** ErrorDetail */
        ErrorDetail: {
            /** Code */
            code: string;
            /** Request Id */
            request_id: string;
        };
        /** ErrorResponse */
        ErrorResponse: {
            error: components["schemas"]["ErrorDetail"];
        };
        /** @enum {string} */
        Market: "ir" | "international";
        /** OrderStatus */
        OrderStatus: {
            /** Failure Code */
            failure_code: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Reservation Expires At */
            reservation_expires_at: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending_reservation" | "awaiting_payment" | "expired" | "cancelled" | "payment_processing" | "payment_review" | "paid" | "refund_pending" | "refunded";
            totals: components["schemas"]["Totals"];
            /** Version */
            version: number;
        };
        /** PreviewResponse */
        PreviewResponse: {
            /** Confirmation */
            confirmation: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /** Groups */
            groups: components["schemas"]["ReviewGroup"][];
            /** Lines */
            lines: components["schemas"]["ReviewLine"][];
            /**
             * Operation Id
             * Format: uuid
             */
            operation_id: string;
            totals: components["schemas"]["Totals"];
        };
        /** ReviewGroup */
        ReviewGroup: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Mode
             * @enum {string}
             */
            mode: "complete_build" | "parts_only";
            /** Name */
            name: string;
            /**
             * Status
             * @enum {string}
             */
            status: "compatible" | "incompatible" | "needs_review" | "incomplete";
        };
        /** ReviewLine */
        ReviewLine: {
            /** Group Id */
            group_id: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Quantity */
            quantity: number;
            /** Unit Price Minor */
            unit_price_minor: number;
        };
        /** Totals */
        Totals: {
            currency: components["schemas"]["Currency"];
            /** Discount Minor */
            discount_minor: number;
            market: components["schemas"]["Market"];
            /** Shipping Minor */
            shipping_minor: number;
            /** Subtotal Minor */
            subtotal_minor: number;
            /** Tax Included */
            tax_included: boolean;
            /** Tax Minor */
            tax_minor: number;
            /** Total Minor */
            total_minor: number;
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
    previewCheckout: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CheckoutIntent"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PreviewResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    confirmCheckout: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                operation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConfirmPreview"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrderStatus"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    readOrderStatus: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                order_id: string;
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
                    "application/json": components["schemas"]["OrderStatus"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Content */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
}
