# Italo
Image transfer tool for Indica Labs' HALO

>[!IMPORTANT]
>Italo requires access to HALO's GraphQL API server with a `scope=serviceuser|graphql` user account. For details on how to create the HALO service client, please see [Step 2](https://gitlab.com/indica_labs_public/example-code#step-2-create-halo-service-client) of Indica Labs' python example.

>[!TIP]
>Upon first start, press the `Search` button. Italo will then write a template configuration file named `secrets.json` to the current folder. Replace the values indicated by squared brackets `[ ]` with your custom configuration values:
>```JSON
>{
>  "client_name": "[GraphQL client name]",
>  "client_secrect": "[GraphQL client secret]",
>  "client_scope": "serviceuser graphql",
>  "grant_type": "client_credentials",
>  "server_name": "[GraphQL server name]"
>}
>```
>Please make sure to limit access to the `secrets.json` file to people you trust with access to HALO's SQL database.

>[!CAUTION]
>Modifying entries in a database or copying files between storage systems bears the risk of unexpected behaviour and failures. HALO's SQL database reports errors during updates and Italo copies files without modification of the source. However, you should favor stable network connections (ethernet > wifi) and avoid tunneling protocols (vpn) to improve your user experience.
