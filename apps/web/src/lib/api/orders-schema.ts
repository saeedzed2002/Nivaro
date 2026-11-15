/** Generated from contracts/openapi/orders.json. Run pnpm contracts:generate. */
export interface paths {
    "/api/v1/admin/orders/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** History */
        get: operations["listStaffOrders"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/orders/{order_id}/fulfillment": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read */
        get: operations["readOrderFulfillment"];
        put?: never;
        /** Change */
        post: operations["changeOrderFulfillment"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
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
    "/api/v1/orders/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** History */
        get: operations["listCustomerOrders"];
        put?: never;
        post?: never;
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
    "/api/v1/orders/{order_id}/details": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Details */
        get: operations["readCustomerOrderDetails"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/orders/{order_id}/payment": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Simulated Payment */
        post: operations["startSimulatedPayment"];
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
        /** @enum {string} */
        Action: "prepare" | "ship" | "deliver";
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
        /** Deliver */
        Deliver: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "deliver";
            /** Expected Version */
            expected_version: number;
        };
        /** DeliveryAddress */
        DeliveryAddress: {
            /** City */
            city: string;
            /** Country */
            country: string;
            /** Postal Code */
            postal_code: string;
            /** Recipient */
            recipient: string;
            /** Street */
            street: string;
        };
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
        /** FulfillmentView */
        FulfillmentView: {
            /** Allowed Actions */
            allowed_actions: components["schemas"]["Action"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending_reservation" | "awaiting_payment" | "expired" | "cancelled" | "payment_processing" | "payment_review" | "paid" | "refund_pending" | "refunded" | "processing" | "shipped" | "delivered";
            /** Timeline */
            timeline: components["schemas"]["StaffTransition"][];
            /** Tracking Reference */
            tracking_reference: string | null;
            /** Version */
            version: number;
        };
        /** HistoryEntry */
        HistoryEntry: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            currency: components["schemas"]["Currency"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            market: components["schemas"]["Market"];
            /**
             * Status
             * @enum {string}
             */
            status: "pending_reservation" | "awaiting_payment" | "expired" | "cancelled" | "payment_processing" | "payment_review" | "paid" | "refund_pending" | "refunded" | "processing" | "shipped" | "delivered";
            /** Total Minor */
            total_minor: number;
        };
        /** @enum {string} */
        Market: "ir" | "international";
        /** OrderDetails */
        OrderDetails: {
            address: components["schemas"]["DeliveryAddress"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            currency: components["schemas"]["Currency"];
            /** Groups */
            groups: components["schemas"]["PurchasedGroup"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            market: components["schemas"]["Market"];
            /** Standalone */
            standalone: components["schemas"]["PurchasedItem"][];
            /**
             * Status
             * @enum {string}
             */
            status: "pending_reservation" | "awaiting_payment" | "expired" | "cancelled" | "payment_processing" | "payment_review" | "paid" | "refund_pending" | "refunded" | "processing" | "shipped" | "delivered";
            /** Timeline */
            timeline: components["schemas"]["StateChange"][];
            /** Total Minor */
            total_minor: number;
            totals: components["schemas"]["Totals"];
            /** Tracking Reference */
            tracking_reference?: string | null;
        };
        /** OrderHistory */
        OrderHistory: {
            /** Next Before */
            next_before: string | null;
            /** Orders */
            orders: components["schemas"]["HistoryEntry"][];
        };
        /** OrderStatus */
        OrderStatus: {
            /** Failure Code */
            failure_code: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Payment State */
            payment_state?: ("queued" | "submitted" | "blocked") | null;
            /** Reservation Expires At */
            reservation_expires_at: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending_reservation" | "awaiting_payment" | "expired" | "cancelled" | "payment_processing" | "payment_review" | "paid" | "refund_pending" | "refunded" | "processing" | "shipped" | "delivered";
            totals: components["schemas"]["Totals"];
            /** Version */
            version: number;
        };
        /** Prepare */
        Prepare: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "prepare";
            /** Expected Version */
            expected_version: number;
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
        /** PurchasedGroup */
        PurchasedGroup: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Items */
            items: components["schemas"]["PurchasedItem"][];
            /**
             * Mode
             * @enum {string}
             */
            mode: "complete_build" | "parts_only";
            /** Name */
            name: string;
        };
        /** PurchasedItem */
        PurchasedItem: {
            /** Name */
            name: string;
            /** Quantity */
            quantity: number;
            /** Sku */
            sku: string;
            /** Slot Key */
            slot_key: string | null;
            /**
             * Source Line Id
             * Format: uuid
             */
            source_line_id: string;
            /** Unit Price Minor */
            unit_price_minor: number;
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
        /** Ship */
        Ship: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "ship";
            /** Expected Version */
            expected_version: number;
            /** Tracking Reference */
            tracking_reference: string;
        };
        /** StaffTransition */
        StaffTransition: {
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** Reason */
            reason: string;
            /** Staff Actor Id */
            staff_actor_id: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "pending_reservation" | "awaiting_payment" | "expired" | "cancelled" | "payment_processing" | "payment_review" | "paid" | "refund_pending" | "refunded" | "processing" | "shipped" | "delivered";
            /** Version */
            version: number;
        };
        /** StartPayment */
        StartPayment: {
            /** Order Version */
            order_version: number;
        };
        /** StateChange */
        StateChange: {
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending_reservation" | "awaiting_payment" | "expired" | "cancelled" | "payment_processing" | "payment_review" | "paid" | "refund_pending" | "refunded" | "processing" | "shipped" | "delivered";
            /** Version */
            version: number;
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
    listStaffOrders: {
        parameters: {
            query?: {
                before?: string | null;
                status?: ("pending_reservation" | "awaiting_payment" | "expired" | "cancelled" | "payment_processing" | "payment_review" | "paid" | "refund_pending" | "refunded" | "processing" | "shipped" | "delivered") | null;
                limit?: number;
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
                    "application/json": components["schemas"]["OrderHistory"];
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
    readOrderFulfillment: {
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
                    "application/json": components["schemas"]["FulfillmentView"];
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
    changeOrderFulfillment: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                order_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Prepare"] | components["schemas"]["Ship"] | components["schemas"]["Deliver"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FulfillmentView"];
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
    listCustomerOrders: {
        parameters: {
            query?: {
                before?: string | null;
                limit?: number;
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
                    "application/json": components["schemas"]["OrderHistory"];
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
    readCustomerOrderDetails: {
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
                    "application/json": components["schemas"]["OrderDetails"];
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
    startSimulatedPayment: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                order_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StartPayment"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
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
