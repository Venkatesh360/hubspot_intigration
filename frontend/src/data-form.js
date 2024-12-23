import { useState } from 'react';
import {
    Box,
    TextField,
    Button,
} from '@mui/material';
import axios from 'axios';

const endpointMapping = {
    'Notion': 'notion',
    'Airtable': 'airtable',
    'Hubspot': 'hubspot'
};

export const DataForm = ({ integrationType, credentials }) => {
    const [loadedData, setLoadedData] = useState(null);
    const endpoint = endpointMapping[integrationType];

    const handleLoad = async () => {
        try {
            const formData = new FormData();
            formData.append('credentials', JSON.stringify(credentials));
            const url = `http://localhost:8000/integrations/${endpoint}${endpoint === 'hubspot' ? '/get_hubspot_items' : '/load'}`;
            const response = await axios.post(url, formData);
            const data = response.data;
            setLoadedData(data);
            console.log(data);
        } catch (e) {
            alert(e?.response?.data?.detail || 'An unexpected error occurred');
        }
    };

    const renderHubspotTable = () => {
        if (!loadedData || loadedData.length === 0) return null;

        const headers = ['ID', 'First Name', 'Last Name', 'Email', 'Creation Time', 'Last Modified Time'];

        return (
            <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '20px' }}>
                <thead>
                    <tr>
                        {headers.map((header, index) => (
                            <th key={index} style={{ padding: '8px', border: '1px solid #ddd', textAlign: 'left' }}>
                                {header}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {loadedData.map((contact) => {
                        const { id, properties, creation_time, last_modified_time } = contact;
                        const { firstname, lastname, email } = properties;
                        return (
                            <tr key={id}>
                                <td style={{ padding: '8px', border: '1px solid #ddd' }}>{id}</td>
                                <td style={{ padding: '8px', border: '1px solid #ddd' }}>{firstname}</td>
                                <td style={{ padding: '8px', border: '1px solid #ddd' }}>{lastname}</td>
                                <td style={{ padding: '8px', border: '1px solid #ddd' }}>{email}</td>
                                <td style={{ padding: '8px', border: '1px solid #ddd' }}>{creation_time}</td>
                                <td style={{ padding: '8px', border: '1px solid #ddd' }}>{last_modified_time}</td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        );
    };

    return (
        <Box display='flex' justifyContent='center' alignItems='center' flexDirection='column' width='100%'>
            <Box display='flex' flexDirection='column' width='100%'>
                <label htmlFor="keyword">Select Keyword:</label>
                <Button
                    onClick={handleLoad}
                    sx={{ mt: 2 }}
                    variant='contained'
                >
                    Load Data
                </Button>
                <Button
                    onClick={() => setLoadedData(null)}
                    sx={{ mt: 1 }}
                    variant='contained'
                >
                    Clear Data
                </Button>
                {loadedData && (
                    <>
                        {endpoint === 'hubspot' ? renderHubspotTable() :
                            <TextField
                                label="Loaded Data"
                                value={JSON.stringify(loadedData, null, 2)}
                                multiline
                                rows={10}
                                sx={{ mt: 2 }}
                                InputLabelProps={{ shrink: true }}
                                disabled
                            />}
                    </>
                )}
            </Box>
        </Box>
    );
};
