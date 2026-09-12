CREATE TABLE IF NOT EXISTS "allocations" (
	"id" varchar(255) PRIMARY KEY NOT NULL,
	"tenant_id" varchar(255) NOT NULL,
	"user_id" varchar(255),
	"resource_type" varchar(50) NOT NULL,
	"allocated" bigint NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "consumptions" (
	"tenant_id" varchar(255) NOT NULL,
	"user_id" varchar(255),
	"resource_type" varchar(50) NOT NULL,
	"consumed" bigint NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "ledger" (
	"id" varchar(255) PRIMARY KEY NOT NULL,
	"tenant_id" varchar(255) NOT NULL,
	"user_id" varchar(255),
	"resource_type" varchar(50) NOT NULL,
	"entry_type" varchar(50) NOT NULL,
	"amount" bigint NOT NULL,
	"balance" bigint NOT NULL,
	"reason" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS "quota_pools" (
	"id" varchar(255) PRIMARY KEY NOT NULL,
	"resource_type" varchar(50) NOT NULL,
	"capacity" bigint NOT NULL,
	"allocated_to_tenants" bigint NOT NULL,
	CONSTRAINT "quota_pools_resource_type_unique" UNIQUE("resource_type")
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "alloc_scope_resource_idx" ON "allocations" ("tenant_id","user_id","resource_type");--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "consumption_scope_resource_idx" ON "consumptions" ("tenant_id","user_id","resource_type");--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "ledger_tenant_idx" ON "ledger" ("tenant_id");--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "ledger_scope_resource_idx" ON "ledger" ("tenant_id","user_id","resource_type","created_at");