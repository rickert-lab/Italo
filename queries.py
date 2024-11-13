"""
Copyright 2024 The Regents of the University of Colorado

This file is part of Italo. Italo is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by the Free Software
Foundation, version 3 of the License or any later version.

Italo is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program.
If not, see <https://www.gnu.org/licenses/gpl-3.0>.

Author:     Christian Rickert <christian.rickert@cuanschutz.edu>
Group:      Human Immune Monitoring Shared Resource (HIMSR)
            University of Colorado, Anschutz Medical Campus

Title:      Italo
Summary:    Italo file transfer tool for HALO v0.11 (2024-11-18)
URL:        https://github.com/rickert-lab/Italo
"""

import aiohttp
import gql
import json
import ssl
from gql.transport.websockets import WebsocketsTransport as gql_WebsocketsTransport


MAX_NODES = 100  # server limit per page


# create a session client for authorized requests
async def get_client(secrets, credentials):
    # configure client transport
    websocket_transport = gql_WebsocketsTransport(
        connect_args={"max_size": 100 * 1024 * 1024},  # 100 MiB limit
        url=f"wss://{secrets['server_name']}/graphql",
        headers={"authorization": f"bearer {credentials['access_token']}"},
        ssl=ssl.create_default_context(),
        keep_alive_timeout=6 * 60 * 60,  # 6 hrs timeout for server response
    )
    # configure session client with transport
    session_client = gql.Client(
        transport=websocket_transport, fetch_schema_from_transport=True
    )
    return session_client


# retrieve server credentials for authentication
async def get_credentials(secrets):
    async with aiohttp.ClientSession() as credentials_session:
        async with credentials_session.request(
            method="Post",
            url=f"https://{secrets['server_name']}/idsrv/connect/token",
            data={
                "client_id": secrets["client_name"],
                "client_secret": secrets["client_secret"],
                "grant_type": "client_credentials",
                "scope": secrets["client_scope"],
            },
            ssl=ssl.create_default_context(),  # None for default SSL check
            raise_for_status=True,
        ) as credentials_response:
            return await credentials_response.json()  # built-in JSON decoder


# load client secrets into dictionary
def get_secrets(secrets_file):
    with open(secrets_file, "r", encoding="utf-8") as secrets_file:
        return json.load(secrets_file)


async def change_location(session=None, image_id=None, new_location=None):
    """Using HALO's GraphQL function `changeImageLocation` to change the location
    of a single image from its current location (file path) to a new location.
    """
    assert session
    assert image_id
    assert new_location
    vars = {"input": {"imageId": image_id, "newLocation": new_location}}
    query = gql.gql(
        r"""
        mutation changeImageLocation($input: ChangeImageLocationInput!) {
          changeImageLocation(input: $input) {
            mutated {
              node {
                id
                location
              }
            }
            failed {
              error
            }
          }
        }
        """
    )
    image = {}
    response = await session.execute(query, variable_values=vars)
    node = response["changeImageLocation"]["mutated"][0]["node"]
    image[node["id"]] = {
        "location": node["location"],
        "error": response["changeImageLocation"]["failed"],
    }
    return image


async def search_images(session=None, text=None, first=MAX_NODES, after=None):
    """Using HALO's GraphQL function `imageSearch` to find all images
    with locations (file paths) that contain the text search string.
    Returns a dictionary with id keys and location values.
    """
    assert session
    assert text
    assert first
    vars = {"text": text, "first": first, "after": after}
    query = gql.gql(
        r"""
          query ImageSearch($text: String!, $first: Int, $after: Cursor) {
            imageSearch(text: $text, first: $first, after: $after) {
              totalCount
              edges {
                node {
                  result {
                    id
                    imageStudies {
                      study {
                        ancestors {
                          ancestor {
                            name
                          }
                        }
                        name
                      }
                    }
                    location
                  }
                }
                cursor
              }
              pageInfo {
                endCursor
                hasNextPage
              }
            }
        }
        """
    )
    images = {}
    while True:
        response = await session.execute(query, variable_values=vars)
        search = response["imageSearch"]
        for edge in search["edges"]:
            node = edge["node"]
            result = node["result"]
            study = result["imageStudies"][0]["study"]
            # assemble study hierarchy
            studies = ""
            for parent in reversed(study["ancestors"]):
                studies += "/" + parent["ancestor"]["name"]
            studies += "/" + study["name"]
            images[result["id"]] = {"location": result["location"], "studies": studies}
        # check for additional pages (more nodes in connection)
        page = search["pageInfo"]
        if page["hasNextPage"]:
            vars["after"] = page["endCursor"]
            continue
        else:  # last page
            total_count = search["totalCount"]
            assert total_count == len(images)
            break
    return images
