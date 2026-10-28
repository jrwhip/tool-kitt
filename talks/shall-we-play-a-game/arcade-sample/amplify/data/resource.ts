import { type ClientSchema, a, defineData } from '@aws-amplify/backend';

const schema = a.schema({
  Placeholder: a
    .model({
      content: a.string(),
    })
    .authorization((allow) => [allow.guest().to(['read']), allow.owner()]),
});

export type Schema = ClientSchema<typeof schema>;

export const data = defineData({
  schema,
  authorizationModes: {
    defaultAuthorizationMode: 'identityPool',
  },
});
