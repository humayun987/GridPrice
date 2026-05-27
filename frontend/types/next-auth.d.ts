import "next-auth";

declare module "next-auth" {
  interface Session {
    accessToken: string;
    role: string;
    status: string;
  }

  interface User {
    accessToken: string;
    role: string;
    status: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken: string;
    role: string;
    status: string;
  }
}